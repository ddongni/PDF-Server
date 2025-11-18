from __future__ import annotations
import logging
import re
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from lxml import etree
import pikepdf

from app.utils.utils import (
    read_datasets_from_pdf,
    read_template_from_pdf,
    parse_xml,
    strip_ns
)
from app.services.pdf_extract_service import (
    _find_base_form_node,
    _collect_leaf_fields,
    Field
)

logger = logging.getLogger(__name__)

NSWILD = "{*}"

# ---------- 작은 유틸 ----------

def is_xml_bytes(b: bytes) -> bool:
    head = b[:200].lstrip()
    return head.startswith(b"<") or b"<?xml" in head[:40].lower()

def qname_local(el: etree._Element) -> str:
    return etree.QName(el).localname

def first_text(node: etree._Element, xp: str) -> Optional[str]:
    t = node.find(xp)
    if t is not None and t.text:
        s = t.text.strip()
        if s:
            return s
    return None

# ---------- PDF/XFA 접근 ----------

def get_xfa_parts(pdf: pikepdf.Pdf) -> List[Tuple[str, pikepdf.Stream]]:
    acro = pdf.Root.get("/AcroForm", None)
    if not acro:
        raise ValueError("AcroForm not found (XFA 아님일 수 있음)")
    
    xfa = acro.get("/XFA", None)
    if not xfa:
        raise ValueError("XFA key not found")
    
    parts: List[Tuple[str, pikepdf.Stream]] = []
    if isinstance(xfa, pikepdf.Array):
        for i in range(0, len(xfa), 2):
            nm = str(xfa[i])
            st = xfa[i + 1]
            parts.append((nm, st))
    elif isinstance(xfa, pikepdf.Stream):
        parts.append(("xfa", xfa))
    return parts

def load_template_roots(pdf_path: Path) -> List[etree._Element]:
    pdf = pikepdf.Pdf.open(str(pdf_path))
    parts = get_xfa_parts(pdf)
    roots: List[etree._Element] = []
    
    # template / form 이름이 붙은 것 우선
    preferred = [(nm, st) for (nm, st) in parts if any(k in nm.lower() for k in ("template", "form"))]
    target = preferred if preferred else parts
    
    for nm, st in target:
        try:
            b = st.read_bytes()
        except Exception:
            continue
        if not is_xml_bytes(b):
            continue
        try:
            roots.append(etree.fromstring(b))
        except Exception:
            continue
    
    if not roots:
        raise ValueError("템플릿 XML을 파싱하지 못했습니다.")
    
    return roots

# ---------- format 정리 ----------

def normalize_picture(fmt: Optional[str]) -> Optional[str]:
    """
    XFA format/picture에서 date/time만 깔끔히 정리해서 돌려줌.
    text/num 마스크(예: text{A9A 9A9})나 단순 입력 패턴은 제외.
    """
    if not fmt:
        return None
    
    s = fmt.strip()
    
    # date{yyyymmdd}, time{h:MM}, num{...}, text{...} 이런 패턴 분해
    m = re.match(r'^\s*(date|time|num|text)\s*\{\s*(.+?)\s*\}\s*$', s, re.I)
    if m:
        kind, inner = m.group(1).lower(), m.group(2)
        s = inner
        if kind in ("text", "num"):
            return None  # 마스크이므로 버림
    
    # 여전히 마스크 스타일이면(예: A9A9, ### 등) 버리기
    if re.search(r'[A9X#]{2,}', s):
        return None
    
    # 대략적인 date/time 토큰 정규화
    s = re.sub(r'[yY]{4}', 'YYYY', s)
    s = re.sub(r'(?<!Y)[yY]{2}(?!Y)', 'YY', s)
    s = re.sub(r'[mM]{2}', 'MM', s)
    s = re.sub(r'(?<!M)[mM](?!M)', 'M', s)
    s = re.sub(r'[dD]{2}', 'DD', s)
    s = re.sub(r'(?<!D)[dD](?!D)', 'D', s)
    s = re.sub(r'[hH]{2}', 'HH', s)
    s = re.sub(r'(?<!H)[hH](?!H)', 'H', s)
    s = re.sub(r'[sS]{2}', 'ss', s)
    s = re.sub(r'(?<!s)s(?!s)', 's', s)
    s = re.sub(r'[aA]{2}', 'AA', s)
    s = re.sub(r'\s+', ' ', s).strip()
    
    return s or None

# ---------- UI 타입 / 옵션 파싱 ----------

def parse_select_items(field_el: etree._Element) -> List[str]:
    items = []
    for t in field_el.findall(f".//{NSWILD}items/{NSWILD}text"):
        txt = (t.text or "").strip()
        if txt:
            items.append(txt)
    
    # 중복 제거 + 순서 유지
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

def caption_text(node: etree._Element) -> Optional[str]:
    for xp in (f".//{NSWILD}caption//{NSWILD}value//{NSWILD}text",
               f".//{NSWILD}caption//{NSWILD}text"):
        t = node.find(xp)
        if t is not None and t.text and t.text.strip():
            return t.text.strip()
    return None

def collect_radio_options_from_group(grp: etree._Element) -> List[str]:
    opts = []
    # exclGroup 아래의 개별 field들의 caption/이름을 옵션으로 사용
    for rf in grp.findall(f".//{NSWILD}field"):
        label = caption_text(rf) or rf.get("name")
        if label:
            opts.append(label.strip())
    
    seen, out = set(), []
    for x in opts:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

def parse_ui_and_format(field_el: etree._Element) -> Tuple[str, Optional[str]]:
    ui_child = field_el.find(f".//{NSWILD}ui/*")
    fmt_raw = first_text(field_el, f".//{NSWILD}format/{NSWILD}picture")
    fmt = normalize_picture(fmt_raw)
    
    if ui_child is None:
        return "text", fmt
    
    local = qname_local(ui_child)
    
    if local == "textEdit":
        return "text", fmt
    if local == "choiceList":
        # select → options 별도 처리
        return "select", None
    if local == "checkButton":
        return "checkbox", None
    if local == "radioButton":
        # 실제로는 exclGroup 기준으로 처리할 예정
        return "radio", None
    if local == "dateTimeEdit":
        if fmt and re.search(r"(H|HH|m|mm|s|ss|AA)", fmt):
            return "time", fmt
        return "date", fmt
    
    # 알 수 없는 UI 타입은 raw 이름으로
    return local, fmt

# ---------- template.xml에서 필드 경로 추출 ----------

def _get_template_field_path(field_elem: etree._Element, root: etree._Element) -> str:
    """template.xml에서 필드의 경로를 반환합니다."""
    path_parts = []
    current = field_elem
    while current is not None and current is not root:
        name = current.get("name")
        if name:
            path_parts.append(name)
        current = current.getparent()
    path_parts.reverse()
    return "/".join(path_parts) if path_parts else ""

# ---------- 메인 파서: type / options / format 수집 ----------

def build_field_type_info(pdf_path: Path) -> Tuple[Dict[str, Dict], Dict[str, Dict], Dict[str, Dict]]:
    """PDF에서 필드 타입 정보를 추출합니다.
    
    Returns:
        (경로별 타입 정보 딕셔너리, 이름별 타입 정보 딕셔너리, JSON 경로별 타입 정보 딕셔너리)
        경로별이 더 정확하므로 우선 사용
    """
    roots = load_template_roots(pdf_path)
    result_by_path: Dict[str, Dict] = {}
    result_by_name: Dict[str, Dict] = {}
    result_by_json_path: Dict[str, Dict] = {}  # JSON 경로 형식으로 저장
    
    # 1) 먼저 exclGroup(라디오 그룹)부터 수집
    for root in roots:
        for grp in root.findall(f".//{NSWILD}exclGroup"):
            gname = grp.get("name")
            if not gname:
                continue
            
            opts = collect_radio_options_from_group(grp)
            entry: Dict[str, object] = {"type": "radio"}
            
            if opts:
                entry["options"] = opts.copy()
            
            # 경로 기반 저장
            grp_path = _get_template_field_path(grp, root)
            if grp_path:
                result_by_path[grp_path] = entry.copy()
                # JSON 경로 형식으로도 저장 (슬래시를 점으로 변환)
                json_path = grp_path.replace("/", ".")
                result_by_json_path[json_path] = entry.copy()
            
            # 이름 기반 저장은 제거 (경로 기반만 사용하여 옵션 섞임 방지)
            # 같은 이름의 필드가 여러 곳에 있을 수 있으므로 경로 기반으로만 저장
    
    # 2) 일반 field[@name] 처리
    for root in roots:
        for fld in root.findall(f".//{NSWILD}field[@name]"):
            name = fld.get("name")
            if not name:
                continue
            
            # 경로 추출
            field_path = _get_template_field_path(fld, root)
            
            # 이미 exclGroup에서 처리한 field 이름과 충돌하는 경우:
            # - 보통 radio 그룹의 개별 field 이름이므로, 경로 기반으로만 저장
            is_radio_conflict = (name in result_by_name and result_by_name[name].get("type") == "radio")
            
            ftype, fmt = parse_ui_and_format(fld)
            entry: Dict[str, Any] = {}
            
            # type 설정
            entry["type"] = ftype
            
            # date/time format
            if ftype in ("date", "time") and fmt:
                entry["format"] = fmt
            
            # select options
            if ftype == "select":
                opts = parse_select_items(fld)
                if opts:
                    entry["options"] = opts.copy()
            
            # 경로 기반 저장 (항상 저장, 더 정확함)
            if field_path:
                result_by_path[field_path] = entry.copy()
                # JSON 경로 형식으로도 저장 (슬래시를 점으로 변환)
                json_path = field_path.replace("/", ".")
                result_by_json_path[json_path] = entry.copy()
            
            # 이름 기반 저장은 제거 (경로 기반만 사용하여 옵션 섞임 방지)
            # 같은 이름의 필드가 여러 곳에 있을 수 있으므로 경로 기반으로만 저장
    
    # 3) format이 text/num 마스크에서 제거되어 아무 것도 없는 경우는 아예 키를 빼줘도 괜찮음
    for k, v in list(result_by_path.items()):
        if "format" in v and not v["format"]:
            v.pop("format", None)
    for k, v in list(result_by_name.items()):
        if "format" in v and not v["format"]:
            v.pop("format", None)
    for k, v in list(result_by_json_path.items()):
        if "format" in v and not v["format"]:
            v.pop("format", None)
    
    return result_by_path, result_by_name, result_by_json_path

# ---------- pdf_filler_service에서 사용하는 함수 ----------

# ---------- datasets.xml 경로와 template.xml 필드 이름 매핑 ----------

def _get_field_path_from_datasets(elem: etree._Element, base_node: etree._Element) -> str | None:
    """datasets.xml에서 필드 요소의 경로를 반환합니다."""
    path_parts = []
    current = elem
    while current is not None and current is not base_node:
        tag = strip_ns(current.tag)
        parent = current.getparent()
        if parent is not None:
            same_siblings = [c for c in parent if strip_ns(c.tag) == tag]
            if len(same_siblings) > 1:
                idx = same_siblings.index(current) + 1  # 1-based
                path_parts.append(f"{tag}[{idx}]")
            else:
                path_parts.append(tag)
        else:
            path_parts.append(tag)
        current = parent
    path_parts.reverse()
    return "/".join(path_parts) if path_parts else None

def _set_type_info_in_nested(obj: dict, path: List[Tuple[str, int]], type_info: Dict[str, Any]) -> None:
    """nested 구조에 타입 정보를 설정합니다. 배열 인덱스도 처리합니다."""
    cur = obj
    for i, (tag, idx) in enumerate(path):
        is_leaf = (i == len(path) - 1)
        
        # cur이 리스트인 경우 처리
        if isinstance(cur, list):
            if not cur:
                cur.append({})
            if not isinstance(cur[0], dict):
                cur[0] = {}
            cur = cur[0]
        
        if not isinstance(cur, dict):
            logger.warning(f"타입 정보 설정 중 cur가 dict가 아님: type={type(cur)}, path={path}")
            return
        
        if idx >= 0:
            # 배열 노드
            cur.setdefault(tag, [])
            arr = cur[tag]
            
            # 배열이 리스트가 아니면 리스트로 변환
            if not isinstance(arr, list):
                arr = []
                cur[tag] = arr
            
            while len(arr) <= idx:
                arr.append({} if not is_leaf else {})
            
            if is_leaf:
                # 리프 노드에 타입 정보 설정
                arr[idx] = type_info
            else:
                if not isinstance(arr[idx], dict):
                    arr[idx] = {}
                cur = arr[idx]
        else:
            # 단일 노드
            if is_leaf:
                # 리프 노드에 타입 정보 설정
                cur[tag] = type_info
            else:
                cur.setdefault(tag, {})
                if not isinstance(cur[tag], dict):
                    cur[tag] = {}
                cur = cur[tag]
                
def extract_field_types_with_path_map(pdf_path: Path) -> Tuple[dict, Dict[str, Dict[str, Any]]]:
    """
    기존 extract_field_types 로직을 그대로 사용하되,
    JSON 경로(full path) -> 타입 정보 map도 함께 반환.
    
    키 추출과 동일하게 datasets.xml과 form.xml의 필드를 모두 포함합니다.
    
    Returns:
        (nested JSON 구조, { "IMM_0800.Page1....": {type, format, options...}, ... })
    """
    # 키 추출, 값 추출과 동일하게 _build_field_template을 사용하여 필드 구조 생성
    # 이렇게 하면 세 함수 모두 동일한 필드 키를 사용합니다
    from app.services.pdf_extract_service import _build_field_template
    
    # 1) template.xml에서 필드 타입 정보 추출 (경로별, 이름별, JSON 경로별)
    field_type_map_by_path, field_type_map_by_name, field_type_map_by_json_path = build_field_type_info(pdf_path)
    logger.info(f"template.xml에서 경로별 {len(field_type_map_by_path)}개, 이름별 {len(field_type_map_by_name)}개, JSON 경로별 {len(field_type_map_by_json_path)}개 필드 타입 정보 추출 완료")
    
    # 2) _build_field_template을 사용하여 필드 템플릿 생성 (키 추출, 값 추출과 동일)
    # 이 템플릿의 구조를 그대로 사용하여 타입 정보를 채워넣습니다
    field_template = _build_field_template(pdf_path)
    base_tag = next(iter(field_template.keys())) if field_template else None
    if not base_tag:
        return {}, {}
    
    json_path_type_map: Dict[str, Dict[str, Any]] = {}
    result: dict = {}
    base_dict: dict = {}
    result[base_tag] = base_dict
    
    # 5) 템플릿의 구조를 그대로 복사하여 타입 정보를 채워넣을 결과 생성
    if base_tag in field_template:
        # 템플릿 구조를 깊은 복사
        import copy
        base_dict = copy.deepcopy(field_template[base_tag])
    else:
        base_dict = {}
    
    result[base_tag] = base_dict
    
    # 타입 정보 조회 헬퍼 함수
    def _get_type_info_for_path(full_json_path: str, field_type_map_by_json_path: dict, field_type_map_by_path: dict, field_type_map_by_name: dict, field_name: str) -> Dict[str, Any]:
        """경로에 대한 타입 정보를 조회합니다. 부모 경로까지 포함하여 정확하게 매칭합니다."""
        type_info: Dict[str, Any] = {}
        
        # 1. JSON 경로 전체로 먼저 찾기 (가장 정확)
        clean_json_path = re.sub(r'\[\d+\]', '', full_json_path)
        if clean_json_path in field_type_map_by_json_path:
            type_info = field_type_map_by_json_path[clean_json_path].copy()
        else:
            # 부분 JSON 경로 매칭 시도 (뒤에서부터 긴 경로부터)
            json_path_segments = clean_json_path.split(".")
            # 최소 2개 세그먼트(부모+필드)부터 시작하여 전체 경로까지
            for i in range(max(0, len(json_path_segments) - 6), len(json_path_segments)):
                partial_json_path = ".".join(json_path_segments[i:])
                if partial_json_path in field_type_map_by_json_path:
                    type_info = field_type_map_by_json_path[partial_json_path].copy()
                    break
        
        # 2. 경로 기반 매칭 시도 (슬래시 형식)
        if not type_info:
            # JSON 경로를 슬래시 경로로 변환
            path_with_slash = clean_json_path.replace(".", "/")
            if path_with_slash in field_type_map_by_path:
                type_info = field_type_map_by_path[path_with_slash].copy()
            else:
                # 부분 경로 매칭 (뒤에서부터 긴 경로부터)
                path_segments = path_with_slash.split("/")
                for i in range(max(0, len(path_segments) - 6), len(path_segments)):
                    partial_path = "/".join(path_segments[i:])
                    if partial_path in field_type_map_by_path:
                        type_info = field_type_map_by_path[partial_path].copy()
                        break
        
        # 3. base_tag를 제거한 경로로도 시도 (template.xml 경로에 base_tag가 포함되어 있을 수 있음)
        if not type_info and clean_json_path.startswith(f"{base_tag}."):
            # base_tag 제거
            path_without_base = clean_json_path[len(base_tag) + 1:]
            # JSON 경로로 시도
            if path_without_base in field_type_map_by_json_path:
                type_info = field_type_map_by_json_path[path_without_base].copy()
            else:
                # 슬래시 경로로 시도
                path_with_slash = path_without_base.replace(".", "/")
                if path_with_slash in field_type_map_by_path:
                    type_info = field_type_map_by_path[path_with_slash].copy()
                else:
                    # 부분 경로 매칭
                    path_segments = path_with_slash.split("/")
                    for i in range(max(0, len(path_segments) - 6), len(path_segments)):
                        partial_path = "/".join(path_segments[i:])
                        if partial_path in field_type_map_by_path:
                            type_info = field_type_map_by_path[partial_path].copy()
                            break
        
        if not type_info:
            type_info = {"type": "text"}
        
        return type_info
    
    # 6) 템플릿의 모든 필드 경로를 순회하며 타입 정보 추출
    # base_dict를 직접 수정하여 값을 교체합니다
    def walk_template_and_set_types(obj, target_obj, current_path: List[str] = None):
        """템플릿을 순회하며 각 필드에 타입 정보를 설정합니다. target_obj를 직접 수정합니다."""
        if current_path is None:
            current_path = []
        
        if isinstance(obj, dict) and isinstance(target_obj, dict):
            for key, value in obj.items():
                new_path = current_path + [key]
                full_json_path = f"{base_tag}.{'.'.join(new_path)}"
                
                if key not in target_obj:
                    continue
                
                if isinstance(value, dict):
                    if isinstance(target_obj[key], dict):
                        walk_template_and_set_types(value, target_obj[key], new_path)
                elif isinstance(value, list):
                    if isinstance(target_obj[key], list):
                        for i, item in enumerate(value):
                            if i >= len(target_obj[key]):
                                break
                            # 배열 인덱스는 경로에 포함하지 않고, 타입 정보 조회 시에만 사용
                            # 배열 인덱스를 제거한 경로로 타입 정보를 조회
                            item_path_without_index = new_path.copy()
                            item_full_path = f"{base_tag}.{'.'.join(item_path_without_index)}"
                            if isinstance(item, (dict, list)):
                                if isinstance(target_obj[key][i], (dict, list)):
                                    # 배열 인덱스를 경로에 포함하지 않고 재귀 호출
                                    walk_template_and_set_types(item, target_obj[key][i], new_path)
                            else:
                                # 리프 노드: 타입 정보 설정 및 값 교체
                                type_info = _get_type_info_for_path(item_full_path, field_type_map_by_json_path, field_type_map_by_path, field_type_map_by_name, key)
                                # 배열 인덱스를 포함한 경로로 저장 (원본 경로 유지)
                                item_path_with_index = new_path + [f"[{i}]"]
                                item_full_path_with_index = f"{base_tag}.{'.'.join(item_path_with_index)}"
                                json_path_type_map[item_full_path_with_index] = type_info
                                # target_obj에서 직접 값 교체
                                target_obj[key][i] = type_info
                else:
                    # 리프 노드 (필드): 타입 정보 설정 및 값 교체
                    type_info = _get_type_info_for_path(full_json_path, field_type_map_by_json_path, field_type_map_by_path, field_type_map_by_name, key)
                    json_path_type_map[full_json_path] = type_info
                    # target_obj에서 직접 값 교체
                    target_obj[key] = type_info
        elif isinstance(obj, list) and isinstance(target_obj, list):
            for i, item in enumerate(obj):
                if i >= len(target_obj):
                    break
                # 배열 인덱스는 경로에 포함하지 않고, 타입 정보 조회 시에만 사용
                # 배열 인덱스를 제거한 경로로 타입 정보를 조회
                if isinstance(item, (dict, list)):
                    if isinstance(target_obj[i], (dict, list)):
                        # 배열 인덱스를 경로에 포함하지 않고 재귀 호출
                        walk_template_and_set_types(item, target_obj[i], current_path)
                else:
                    # 리프 노드: 타입 정보 설정 및 값 교체
                    item_full_path = f"{base_tag}.{'.'.join(current_path)}" if current_path else base_tag
                    field_name = current_path[-1] if current_path else ""
                    type_info = _get_type_info_for_path(item_full_path, field_type_map_by_json_path, field_type_map_by_path, field_type_map_by_name, field_name)
                    # 배열 인덱스를 포함한 경로로 저장 (원본 경로 유지)
                    item_path_with_index = current_path + [f"[{i}]"]
                    item_full_path_with_index = f"{base_tag}.{'.'.join(item_path_with_index)}"
                    json_path_type_map[item_full_path_with_index] = type_info
                    # target_obj에서 직접 값 교체
                    target_obj[i] = type_info
    
    # 템플릿 구조를 순회하며 타입 정보 설정
    if base_tag in field_template:
        walk_template_and_set_types(field_template[base_tag], base_dict)
    
    found_count = len(json_path_type_map)
    
    logger.info(f"템플릿 기반 필드 타입 추출 완료: {found_count}개 필드의 타입 정보 추출 완료")
    logger.debug(f"JSON 경로별 타입 정보: {len(json_path_type_map)}개")
    
    return result, json_path_type_map

def extract_field_types(pdf_path: Path) -> dict:
    """기존 API 유지: nested JSON만 필요할 때 사용"""
    result, _ = extract_field_types_with_path_map(pdf_path)
    return result