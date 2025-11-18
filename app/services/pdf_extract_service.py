from __future__ import annotations
import re
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Any
from lxml import etree as LET

from fastapi import HTTPException

from app.utils.utils import read_datasets_from_pdf, parse_xml, strip_ns

logger = logging.getLogger(__name__)

# ============== XML 유틸 ==============
def _find_base_form_node(xml_bytes: bytes) -> tuple[LET._Element, str]:
    """
    datasets / form 둘 다에서 공통으로 쓰는 base 노드 탐색:
    - xfa:data가 있으면 그 아래 첫 자식
    - 없으면 xfa:form / form
    - 그것도 없으면 루트
    """
    root = parse_xml(xml_bytes)

    # data 노드 우선
    data_nodes = root.xpath("//*[local-name()='data']")
    data_node = data_nodes[0] if data_nodes else None
    if data_node is not None and len(data_node):
        children = [c for c in data_node if isinstance(c.tag, str)]
        if children:
            return children[0], strip_ns(children[0].tag)

    # form 노드 사용
    form_nodes = root.xpath("//*[local-name()='form']")
    if form_nodes:
        return form_nodes[0], strip_ns(form_nodes[0].tag)

    # fallback: 루트
    return root, strip_ns(root.tag)


# ============== 경로/반복 인덱스 계산 ==============
def _xpath_from_to(elem: LET._Element, base: LET._Element) -> str:
    """
    base를 루트로 하는 상대 XPath (예: './Page2/Contact/Email')
    동일 태그 반복 시 [n] (1-based) 부여
    """
    parts: List[str] = []
    cur = elem
    while cur is not None and cur is not base:
        parent = cur.getparent()
        tag = strip_ns(cur.tag)
        if parent is not None:
            same = [c for c in parent if strip_ns(c.tag) == tag]
            if len(same) > 1:
                idx = same.index(cur) + 1
                parts.append(f"{tag}[{idx}]")
            else:
                parts.append(tag)
        else:
            parts.append(tag)
        cur = parent
    parts.reverse()
    return "./" + "/".join(parts) if parts else "."

def _path_with_index(elem: LET._Element, base: LET._Element) -> List[Tuple[str, int]]:
    """
    JSON 키 생성을 위한 (tag, idx) 경로. idx=-1은 단일, >=0는 배열 위치.
    """
    rev: List[Tuple[str, int]] = []
    cur = elem
    while cur is not None and cur is not base:
        parent = cur.getparent()
        tag = strip_ns(cur.tag)
        idx = -1
        if parent is not None:
            same = [c for c in parent if strip_ns(c.tag) == tag]
            if len(same) > 1:
                idx = same.index(cur)  # 0-based for JSON
        rev.append((tag, idx))
        cur = parent
    rev.reverse()
    return rev  # base 태그는 포함하지 않음

# ============== JSON 스키마 빌더 ==============
def _set_in_nested(obj: dict, path: List[Tuple[str, int]]) -> None:
    if not path:
        return
    
    cur = obj
    for i, (tag, idx) in enumerate(path):
        is_leaf = (i == len(path) - 1)

        if idx >= 0:
            # 배열 노드
            # cur이 배열인 경우 처리 (이전 단계에서 배열 인덱스가 있었을 수 있음)
            if isinstance(cur, list):
                # 배열인 경우 첫 번째 요소를 사용하거나 오류
                if not cur:
                    cur.append({})
                # 첫 번째 요소 사용
                if not isinstance(cur[0], dict):
                    cur[0] = {}
                cur = cur[0]
            
            if not isinstance(cur, dict):
                # 이 경우는 구조 충돌이 난 것 → dict 로 승격
                # (여기까지 오면 이미 parent가 잘못된 타입인 거라 그냥 덮어써도 무방)
                logger.warning(f"배열 노드 처리 중 cur가 dict가 아님: type={type(cur)}, path={path}")
                return

            cur.setdefault(tag, [])
            arr = cur[tag]
            
            # 배열이 리스트가 아니면 리스트로 변환
            if not isinstance(arr, list):
                # 기존 값이 문자열이면 배열로 변환
                existing_val = arr
                arr = [existing_val] if existing_val != "" else []
                cur[tag] = arr

            while len(arr) <= idx:
                arr.append({} if not is_leaf else "")

            if is_leaf:
                # leaf 값은 ""로 유지
                if isinstance(arr[idx], dict):
                    arr[idx] = ""
            else:
                # 중간 노드인데 배열 원소가 str이면 dict로 승격
                if not isinstance(arr[idx], dict):
                    arr[idx] = {}
                cur = arr[idx]

        else:
            # 단일 노드
            # cur이 배열인 경우 처리 (이전 단계에서 배열 인덱스가 있었을 수 있음)
            if isinstance(cur, list):
                # 배열인 경우 첫 번째 요소를 사용하거나 오류
                if not cur:
                    cur.append({})
                # 첫 번째 요소 사용
                if not isinstance(cur[0], dict):
                    cur[0] = {}
                cur = cur[0]
            
            if not isinstance(cur, dict):
                # 구조가 꼬인 경우: dict로 변환 불가능하면 스킵
                logger.warning(f"단일 노드 처리 중 cur가 dict가 아님: type={type(cur)}, path={path}")
                return
                
            if is_leaf:
                # leaf 인데 기존에 dict가 있으면 그대로 두고, 아니면 ""로 설정
                existing = cur.get(tag)
                if not isinstance(existing, dict):
                    cur[tag] = ""
            else:
                # 중간 노드: 반드시 dict 여야 함
                existing = cur.get(tag)
                if not isinstance(existing, dict):
                    # 기존 값이 배열이면 배열의 첫 번째 요소를 사용하거나 배열을 유지
                    if isinstance(existing, list):
                        # 배열인 경우: 배열의 첫 번째 요소를 사용하거나, 배열을 유지하고 경로를 건너뜀
                        # 이는 form.xml에서 배열 인덱스가 없는 경로를 처리할 때 발생할 수 있음
                        # 예: KeepPageSeparate가 배열인데 KeepPageSeparate.FamilyMember로 접근
                        # 이 경우 배열의 각 요소에 대해 처리해야 하지만, 템플릿 생성 시에는 첫 번째 요소만 사용
                        if existing and isinstance(existing[0], dict):
                            cur = existing[0]
                            # tag는 이미 처리되었으므로 continue로 다음 경로로 이동
                            continue
                        else:
                            # 배열이 비어있거나 첫 번째 요소가 dict가 아니면 스킵
                            logger.debug(f"중간 노드가 배열임 (스킵): tag={tag}, path={path}")
                            return
                    else:
                        cur[tag] = {}
                cur = cur[tag]

# ============== 필드 수집(leaf 노드) ==============
@dataclass
class Field:
    elem: LET._Element
    rel_xpath: str
    json_path: List[Tuple[str, int]]
    key_for_map: str

def _is_leaf(el: LET._Element) -> bool:
    # 자식 element가 없고(텍스트/공백만 있을 수 있음) → leaf 취급
    # 또는 자식 element가 있지만 텍스트 값도 있는 경우 → leaf 취급 (예: <FamilyMember>123</FamilyMember>)
    has_text = (el.text and el.text.strip()) or False
    has_children = any(isinstance(c.tag, str) for c in el)
    # 텍스트가 있으면 leaf로 취급 (자식 element가 있어도)
    if has_text:
        return True
    # 텍스트가 없고 자식 element만 있으면 leaf가 아님
    return not has_children

def _has_data_group_ancestor(el: LET._Element) -> bool:
    """
    노드나 그 조상 노드 중 하나가 xfa:dataNode="dataGroup" 속성을 가지는지 확인합니다.
    """
    # XFA 데이터 네임스페이스
    xfa_ns = "http://www.xfa.org/schema/xfa-data/1.0/"
    data_node_attr = f"{{{xfa_ns}}}dataNode"
    
    cur = el
    while cur is not None:
        # 현재 노드가 xfa:dataNode="dataGroup" 속성을 가지는지 확인
        data_node_value = cur.get(data_node_attr)
        if data_node_value == "dataGroup":
            return True
        cur = cur.getparent()
    return False

def _collect_leaf_fields(base: LET._Element) -> List[Field]:
    fields: List[Field] = []
    for el in base.iter():
        if not isinstance(el.tag, str):
            continue
        # xfa:dataNode="dataGroup" 속성을 가진 노드나 그 자식은 제외
        if _has_data_group_ancestor(el):
            continue
        if _is_leaf(el):
            rx = _xpath_from_to(el, base)
            jp = _path_with_index(el, base)
            key = ".".join([f"{t}[{i}]" if i >= 0 else t for t, i in jp])
            # 버튼 필드 제외 (SaveButton, ResetButton, PrintButton)
            # 태그 이름에서 버튼 필드 확인
            tag_name = LET.QName(el).localname if hasattr(LET, 'QName') else el.tag.split('}')[-1] if '}' in el.tag else el.tag
            if any(btn in tag_name for btn in ["SaveButton", "ResetButton", "PrintButton"]):
                continue
            fields.append(Field(elem=el, rel_xpath=rx, json_path=jp, key_for_map=key))
    # 중복 키 방지
    seen: Dict[str, int] = {}
    for f in fields:
        n = seen.get(f.key_for_map, 0)
        if n > 0:
            f.key_for_map = f.key_for_map + f"__%d" % (n + 1)
        seen[f.key_for_map] = n + 1
    return fields

# ============== JSON 템플릿 생성 ==============
def _build_json_template(base_tag: str, fields: List[Field]) -> dict:
    tpl: dict = {}
    for f in fields:
        _set_in_nested(tpl, f.json_path)
    return {base_tag: tpl}

# ============== 유틸리티 함수 ==============
def _get_base_dir() -> Path:
    """프로젝트 루트 디렉토리 반환"""
    return Path(__file__).parent.parent.parent

def _validate_pdf_file(filename: str | None, contents: bytes) -> None:
    """PDF 파일 검증"""
    if not filename:
        raise HTTPException(status_code=400, detail="파일명이 없습니다. 파일을 선택해주세요.")
    
    if not filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다.")
    
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")

def _calculate_checksum(contents: bytes) -> str:
    """파일 체크섬 계산"""
    return hashlib.sha256(contents).hexdigest()

def _is_file_identical(file_path: Path, contents: bytes) -> bool:
    """기존 파일과 동일한지 확인"""
    if not file_path.exists():
        return False
    
    try:
        with open(file_path, "rb") as f:
            existing_checksum = _calculate_checksum(f.read())
        upload_checksum = _calculate_checksum(contents)
        return existing_checksum == upload_checksum
    except Exception as e:
        logger.error(f"파일 비교 중 오류: {e}")
        return False

# ============== 메인 파이프라인 ==============
def _build_field_template(pdf_path: Path) -> dict:
    """
    PDF에서 datasets.xml과 form.xml을 모두 사용하여 필드 키를 추출하고
    빈 문자열로 채워진 JSON 템플릿을 생성합니다.
    
    Returns:
        필드 구조를 담은 JSON 딕셔너리 (값은 빈 문자열)
    """
    # 1) datasets.xml 추출
    datasets_bytes = read_datasets_from_pdf(pdf_path)
    base_node, base_tag = _find_base_form_node(datasets_bytes)
    fields = _collect_leaf_fields(base_node)

    # 2) JSON 템플릿 생성 (datasets 기반)
    json_tpl = _build_json_template(base_tag, fields)
    
    # datasets.xml에서 KeepPageSeparate 배열 구조 확인 (form.xml 경로 매핑용)
    # KeepPageSeparate 인덱스별로 필드 경로 그룹화
    keep_page_separate_groups: Dict[int, set] = {}
    for field in fields:
        for i, (tag, idx) in enumerate(field.json_path):
            if tag == "KeepPageSeparate" and idx >= 0:
                # KeepPageSeparate 이후의 경로 추출 (태그 이름만)
                keep_tail_tags = tuple(t for t, _ in field.json_path[i+1:])
                if idx not in keep_page_separate_groups:
                    keep_page_separate_groups[idx] = set()
                keep_page_separate_groups[idx].add(keep_tail_tags)
                break
    
    # 3) form.xml에서도 필드 경로 수집하여 추가
    form_base_tag, form_field_paths = _collect_form_field_paths_from_pdf(pdf_path)
    if form_base_tag and form_field_paths:
        if form_base_tag != base_tag:
            logger.warning(
                f"datasets base_tag={base_tag}, form base_tag={form_base_tag} 불일치"
            )

        # 같은 경로의 필드가 여러 번 나오는지 확인
        path_tails: List[List[str]] = []
        for path_segments in form_field_paths:
            if not path_segments:
                continue

            # base_tag 위치 찾기
            if base_tag in path_segments:
                idx = path_segments.index(base_tag)
                tail = path_segments[idx + 1:]  # ["Page1", "ContactInformation", ...]
            else:
                # base_tag가 없으면 첫 요소 버리고 tail 사용 (form1 방지용)
                tail = path_segments[1:] if len(path_segments) > 1 else []

            if tail:
                path_tails.append(tail)
        
        # 같은 경로가 여러 번 나오는지 카운트
        path_count: Dict[tuple, int] = {}
        for tail in path_tails:
            path_key = tuple(tail)
            path_count[path_key] = path_count.get(path_key, 0) + 1
        
        # 각 경로 접두사(prefix)가 여러 번 나오는지 카운트
        # 예: ("Page1", "KeepPageSeparate")가 여러 번 나오면 KeepPageSeparate에 배열 인덱스 추가
        # 중요: KeepPageSeparate 같은 경우, ("Page1", "KeepPageSeparate") 접두사가 여러 번 나오면
        # KeepPageSeparate에 배열 인덱스를 추가해야 함
        prefix_count: Dict[tuple, int] = {}
        for tail in path_tails:
            for i in range(1, len(tail) + 1):
                prefix = tuple(tail[:i])
                prefix_count[prefix] = prefix_count.get(prefix, 0) + 1
        
        # KeepPageSeparate 같은 경우를 위해 특별 처리
        # ("Page1", "KeepPageSeparate") 접두사가 여러 번 나오는지 확인
        keep_page_separate_prefix = ("Page1", "KeepPageSeparate")
        
        # 경로를 추가 (중복이 있으면 배열로 처리)
        # 같은 경로가 나온 횟수를 추적
        seen_paths: Dict[tuple, int] = {}
        # KeepPageSeparate 같은 경우를 위해 접두사별 인덱스 추적
        prefix_seen: Dict[tuple, int] = {}
        
        for tail in path_tails:
            try:
                path_key = tuple(tail)
                count = path_count[path_key]
                
                if not tail:
                    # 빈 경로는 스킵
                    continue
                
                # KeepPageSeparate 같은 경우를 위해 접두사 확인
                # ("Page1", "KeepPageSeparate") 접두사가 여러 번 나오면 KeepPageSeparate에 배열 인덱스 추가
                keep_prefix = ("Page1", "KeepPageSeparate")
                if len(tail) >= 2 and tuple(tail[:2]) == keep_prefix and prefix_count.get(keep_prefix, 0) > 1:
                    # KeepPageSeparate 접두사가 여러 번 나오는 경우
                    # datasets.xml의 KeepPageSeparate 구조를 기준으로 인덱스 매핑
                    keep_tail_tags = tuple(tail[2:])  # KeepPageSeparate 이후의 태그들만
                    
                    # datasets.xml에서 같은 태그 경로를 가진 KeepPageSeparate 인덱스 찾기
                    keep_idx = -1
                    for ds_idx, ds_tag_set in keep_page_separate_groups.items():
                        if keep_tail_tags in ds_tag_set:
                            keep_idx = ds_idx
                            break
                        # 부분 일치 확인 (예: FamilyMember.OptionsQ2가 FamilyMember 그룹에 포함)
                        for ds_tags in ds_tag_set:
                            # keep_tail_tags의 첫 번째 태그가 ds_tags에 포함되어 있는지 확인
                            if len(keep_tail_tags) > 0 and len(ds_tags) > 0:
                                if keep_tail_tags[0] == ds_tags[0]:
                                    # 첫 번째 태그가 일치하면 같은 KeepPageSeparate로 간주
                                    keep_idx = ds_idx
                                    break
                        if keep_idx >= 0:
                            break
                    
                    # datasets.xml에 없는 경로인 경우, 순서대로 할당 (최대 3개까지만)
                    if keep_idx == -1:
                        # KeepPageSeparate 접두사별로 순서대로 인덱스 할당
                        # 첫 번째 태그를 기준으로 그룹화 (예: FamilyMember로 시작하는 경로는 같은 KeepPageSeparate)
                        first_tag = keep_tail_tags[0] if keep_tail_tags else None
                        keep_prefix_key = (keep_prefix, first_tag) if first_tag else keep_prefix
                        
                        if keep_prefix_key not in prefix_seen:
                            prefix_seen[keep_prefix_key] = {}
                        if keep_tail_tags not in prefix_seen[keep_prefix_key]:
                            # 기존 KeepPageSeparate 배열의 길이 확인 (최대 3개)
                            existing_keep = json_tpl[base_tag].get("Page1", {}).get("KeepPageSeparate", [])
                            if isinstance(existing_keep, list):
                                # 첫 번째 태그가 FamilyMember인 경우, 기존 FamilyMember가 있는 KeepPageSeparate 인덱스 찾기
                                if first_tag == "FamilyMember":
                                    # FamilyMember가 있는 KeepPageSeparate 인덱스 찾기
                                    for i, item in enumerate(existing_keep):
                                        if isinstance(item, dict) and "FamilyMember" in item:
                                            new_idx = i
                                            break
                                    else:
                                        new_idx = min(len(existing_keep), 2)
                                else:
                                    new_idx = min(len(existing_keep), 2)
                            else:
                                new_idx = 0
                            prefix_seen[keep_prefix_key][keep_tail_tags] = new_idx
                        keep_idx = prefix_seen[keep_prefix_key][keep_tail_tags]
                        # 최대 인덱스 2로 제한
                        keep_idx = min(keep_idx, 2)
                    
                    # KeepPageSeparate에 배열 인덱스 추가
                    json_path = [(tail[0], -1), (tail[1], keep_idx)]
                    # 나머지 경로 추가
                    for tag in tail[2:]:
                        json_path.append((tag, -1))
                    
                    # KeepPageSeparate 경로를 템플릿에 추가
                    _set_in_nested(json_tpl[base_tag], json_path)
                elif count > 1:
                    # 같은 경로가 여러 번 나오면 배열로 처리
                    # 현재까지 같은 경로가 몇 번 나왔는지 확인
                    if path_key not in seen_paths:
                        seen_paths[path_key] = 0
                    else:
                        seen_paths[path_key] += 1
                    current_idx = seen_paths[path_key]
                    
                    # 가장 짧은 공통 접두사를 찾아서 그 위치에 배열 인덱스 추가
                    # 범용적인 방법: 각 위치에서 같은 이름이 여러 번 나오는지 확인
                    # 예: ["Page1", "KeepPageSeparate", "FamilyMember"]가 여러 번 나오면
                    # "KeepPageSeparate"에 배열 인덱스 추가
                    json_path = []
                    array_idx_added = False
                    
                    # 범용적인 배열 인덱스 위치 찾기
                    # 전략: 같은 경로가 여러 번 나올 때, 가장 짧은 공통 접두사를 찾아서
                    # 그 위치에 배열 인덱스를 추가합니다.
                    # 이는 다양한 PDF 구조에서도 작동합니다.
                    for i, tag in enumerate(tail):
                        # 이전 경로까지의 접두사
                        prev_prefix = tuple(tail[:i])
                        # 현재 태그를 포함한 접두사
                        current_prefix = tuple(tail[:i+1])
                        
                        # 이전 접두사가 한 번만 나오고, 현재 접두사가 여러 번 나오면
                        # 현재 태그에 배열 인덱스 추가 (가장 짧은 공통 접두사)
                        # 이 로직은 다음과 같은 경우들을 처리합니다:
                        # 1. ["Page1", "A", "B"]가 여러 번 → A[0], A[1]에 각각 B
                        # 2. ["Page1", "A", "B", "C"]와 ["Page1", "A", "B", "D"] → A는 한 번, B는 여러 번이면 B에 인덱스
                        prev_cnt = prefix_count.get(prev_prefix, 0)
                        current_cnt = prefix_count.get(current_prefix, 0)
                        
                        if prev_cnt == 1 and current_cnt > 1 and not array_idx_added:
                            # 현재 태그가 반복되는 첫 번째 위치
                            json_path.append((tag, current_idx))
                            array_idx_added = True
                        elif i == len(tail) - 1 and not array_idx_added:
                            # 마지막 태그이고 아직 배열 인덱스를 추가하지 않았으면
                            # (전체 경로가 반복되는 경우 - fallback)
                            json_path.append((tag, current_idx))
                        else:
                            json_path.append((tag, -1))
                else:
                    # 단일 값으로 처리
                    json_path = [(t, -1) for t in tail]
                
                _set_in_nested(json_tpl[base_tag], json_path)
            except Exception as e:
                logger.error(f"경로 추가 중 오류: tail={tail}, path_key={path_key if 'path_key' in locals() else 'N/A'}, 오류={type(e).__name__}: {str(e)}")
                import traceback
                logger.error(f"상세 오류: {traceback.format_exc()}")
                # 오류가 발생해도 계속 진행
                continue
    
    return json_tpl

def _collect_form_field_paths_from_pdf(pdf_path: Path) -> tuple[str | None, List[List[str]]]:
    """
    XFA form 스트림에서 필드 경로를 수집하여 반환합니다.
    값이 없어도 필드 경로만 수집합니다.
    
    Returns:
        (base_tag, [필드 경로 리스트])
        예: ("IMM_0800", [["Page1", "ContactInformation", "Information", "TelephoneNo"], ...])
    """
    form_bytes = _read_form_from_pdf(pdf_path)
    if not form_bytes:
        return None, []

    try:
        root = LET.fromstring(form_bytes)
    except Exception as e:
        logger.warning(f"form XML 파싱 실패: {e}")
        return None, []

    # 기본 base_tag: 최상위 subform name (예: IMM_0800)
    base_sub = None
    base_tag = None
    for sf in root.findall(".//{*}subform"):
        name = sf.get("name")
        if name:
            base_sub = sf
            base_tag = name
            break

    if base_sub is None or base_tag is None:
        return None, []

    field_paths: List[List[str]] = []

    def walk(node: LET._Element, path_segments: List[str]):
        for child in node:
            if not isinstance(child.tag, str):
                continue
            # xfa:dataNode="dataGroup" 속성을 가진 노드나 그 자식은 제외
            if _has_data_group_ancestor(child):
                continue
            lname = LET.QName(child).localname

            if lname == "subform":
                name = child.get("name")
                if name:
                    walk(child, path_segments + [name])
                else:
                    walk(child, path_segments)
            elif lname == "exclGroup":
                # exclGroup은 라디오 버튼 그룹으로, 그 자체가 필드입니다
                gname = child.get("name")
                if gname:
                    field_paths.append(path_segments + [gname])
                    # exclGroup 내부의 field들(No, Yes 등)은 별도 필드가 아니므로 재귀하지 않음
                    # exclGroup 자체만 필드로 취급
                # exclGroup 내부는 처리하지 않음 (라디오 버튼 옵션은 별도 필드가 아님)
            elif lname == "field":
                fname = child.get("name")
                if not fname:
                    continue
                # 버튼 필드 제외 (SaveButton, ResetButton, PrintButton)
                if any(btn in fname for btn in ["SaveButton", "ResetButton", "PrintButton"]):
                    continue
                # 값이 없어도 필드 경로는 수집
                field_paths.append(path_segments + [fname])
            else:
                walk(child, path_segments)

    # 시작 path: [base_tag]
    walk(base_sub, [base_tag])

    return base_tag, field_paths

def extract_fields_from_pdf(pdf_path: Path) -> dict:
    """PDF에서 필드를 추출하여 JSON 템플릿을 반환합니다.
    
    Args:
        pdf_path: PDF 파일 경로
    
    Returns:
        추출된 필드 정보를 담은 JSON 딕셔너리 (값은 빈 문자열)
    """
    # 공통 함수로 필드 템플릿 생성
    json_tpl = _build_field_template(pdf_path)
    
    return json_tpl


# ============== form XML 읽기 ==============
def _read_xfa_part_from_pdf(pdf_path: Path, part_name: str) -> bytes | None:
    """
    XFA /XFA 배열에서 특정 파트 이름을 찾아 그대로 반환.
    
    Args:
        pdf_path: PDF 파일 경로
        part_name: 찾을 파트 이름 (예: "form", "datasets", "template")
    
    Returns:
        파트의 바이트 데이터 또는 None
    """
    try:
        import pikepdf

        with pikepdf.open(str(pdf_path)) as pdf:
            acro = pdf.Root.get("/AcroForm", None)
            if not acro:
                return None
            xfa = acro.get("/XFA", None)
            if not xfa:
                return None

            # Array 형태: [name1, stream1, name2, stream2, ...]
            if isinstance(xfa, pikepdf.Array):
                parts = list(xfa)
                for i in range(0, len(parts), 2):
                    name = str(parts[i]) if i < len(parts) else ""
                    if part_name.lower() in name.lower():
                        st = parts[i + 1]
                        return st.read_bytes()
            # 단일 스트림인 경우: 전체 XDP가 들어있으므로 그대로 반환
            elif isinstance(xfa, pikepdf.Stream):
                return xfa.read_bytes()
    except Exception as e:
        logger.warning(f"XFA {part_name} 읽기 실패: {e}")
    return None

def _read_form_from_pdf(pdf_path: Path) -> bytes | None:
    """
    XFA /XFA 배열에서 이름에 'form' 이 포함된 파트를 찾아 그대로 반환.
    IRCC IMM 계열처럼 array 구조인 폼을 기준으로 함.
    """
    return _read_xfa_part_from_pdf(pdf_path, "form")
    
# ============== 값 추출 ==============
def _set_value_in_nested(obj: dict, path: List[Tuple[str, int]], value: str, preserve_structure: bool = False) -> bool:
    """
    중첩된 JSON 구조에 값을 설정합니다.
    
    Args:
        obj: 대상 JSON 객체
        path: 경로 리스트, 예: [("Page1", -1), ("KeepPageSeparate", 0), ("FamilyMember", -1)]
        value: 설정할 값
        preserve_structure: True이면 기존 구조를 유지하고 값만 설정 (구조가 없으면 False 반환)
    
    Returns:
        성공 여부 (preserve_structure=True일 때 구조가 없으면 False)
    """
    cur = obj
    for i, (tag, idx) in enumerate(path):
        is_leaf = (i == len(path) - 1)
        if idx >= 0:
            # 배열 노드
            if not isinstance(cur, dict):
                if preserve_structure:
                    return False
                cur = {}
            if preserve_structure and tag not in cur:
                return False
            cur.setdefault(tag, [])
            arr = cur[tag]
            
            # 배열이 리스트가 아니면 리스트로 변환
            if not isinstance(arr, list):
                if preserve_structure:
                    return False
                arr = []
                cur[tag] = arr
            
            # 배열을 필요한 크기까지 확장
            # preserve_structure=False일 때는 배열을 확장
            if not preserve_structure:
                while len(arr) <= idx:
                    arr.append({} if not is_leaf else "")
            
            # 인덱스 범위 체크
            if idx < 0:
                logger.warning(f"배열 인덱스가 음수: idx={idx}, path={path}")
                return False
            if idx >= len(arr):
                # 배열 확장 후에도 범위를 벗어나면 오류
                logger.warning(f"배열 인덱스 범위 초과: idx={idx}, len(arr)={len(arr)}, path={path}, preserve_structure={preserve_structure}")
                if preserve_structure:
                    # preserve_structure=True일 때도 배열을 확장 (템플릿에 배열이 있지만 인덱스가 부족한 경우)
                    # 이는 템플릿 생성 시 배열 크기를 정확히 예측하지 못한 경우를 처리하기 위함
                    while len(arr) <= idx:
                        arr.append({} if not is_leaf else "")
                else:
                    # preserve_structure=False일 때는 배열을 더 확장
                    while len(arr) <= idx:
                        arr.append({} if not is_leaf else "")
            
            if is_leaf:
                # leaf 노드: 값 설정
                arr[idx] = value
            else:
                # 중간 노드: dict로 변환 필요
                if not isinstance(arr[idx], dict):
                    if preserve_structure:
                        return False
                    # 이미 문자열이나 다른 타입이면 dict로 변환
                    arr[idx] = {}
                cur = arr[idx]
        else:
            # 단일 노드
            if not isinstance(cur, dict):
                if preserve_structure:
                    return False
                # 구조가 꼬인 경우: dict로 변환 불가능하면 스킵
                logger.warning(f"중간 노드가 dict가 아님: type={type(cur)}, path={path}")
                return False
            if preserve_structure and tag not in cur:
                return False
            if is_leaf:
                cur[tag] = value
            else:
                cur.setdefault(tag, {})
                # 기존 값이 dict가 아니면 dict로 변환
                if not isinstance(cur[tag], dict):
                    if preserve_structure:
                        return False
                    cur[tag] = {}
                cur = cur[tag]
    return True

def extract_field_values(pdf_path: Path) -> dict:
    """
    PDF에서 필드 구조를 추출하고 실제 값을 채워서 반환합니다.
    
    Returns:
        필드 구조와 값이 포함된 JSON 딕셔너리
    """
    # re 모듈 명시적 import (순환 import 문제 방지)
    import re
    
    # 1) 공통 함수로 필드 템플릿 생성 (빈 문자열로)
    # 이 함수는 datasets.xml과 form.xml의 모든 필드 경로를 포함합니다
    # 중요: extract_fields_from_pdf와 동일한 함수를 사용하여 필드 키가 일치하도록 보장
    json_tpl = _build_field_template(pdf_path)
    base_tag = next(iter(json_tpl.keys())) if json_tpl else None
    if not base_tag:
        return json_tpl

    # 2) datasets.xml에서 값 채우기
    # 중요: _build_field_template에서 사용한 것과 동일한 방식으로 필드 수집
    datasets_bytes = read_datasets_from_pdf(pdf_path)
    base_node, _ = _find_base_form_node(datasets_bytes)
    fields = _collect_leaf_fields(base_node)
    
    # 필드 타입 정보 가져오기 (라디오 버튼 필드 검증용)
    # 순환 import 방지를 위해 함수 내부에서 import
    from app.services.pdf_field_type_service import extract_field_types_with_path_map
    _, json_path_type_map = extract_field_types_with_path_map(pdf_path)
    
    success_count = 0
    fail_count = 0
    skipped_count = 0  # 값이 없어서 스킵된 필드 수
    for field in fields:
        v = (field.elem.text or "").strip()
        
        # JSON 경로 생성
        json_parts = []
        for tag, idx in field.json_path:
            if idx >= 0:
                json_parts.append(f"{tag}[{idx}]")
            else:
                json_parts.append(tag)
        json_path = f"{base_tag}.{'.'.join(json_parts)}"
        
        # 값이 없는 경우에도 추출 시도 (빈 문자열로라도)
        
        # 라디오 버튼 필드의 경우, 값이 옵션 목록에 있는지 확인
        clean_json_path = re.sub(r'\[\d+\]', '', json_path)
        field_type_info = json_path_type_map.get(clean_json_path) or json_path_type_map.get(json_path)
        
        if field_type_info and field_type_info.get("type") == "radio":
            options = field_type_info.get("options", [])
            # 값이 옵션 목록에 없으면 변환 시도
            if options and v and v not in options:
                # 일반적인 값 변환: "Y" -> "Yes", "N" -> "No"
                value_map = {"Y": "Yes", "N": "No", "1": "Yes", "0": "No"}
                if v in value_map and value_map[v] in options:
                    v = value_map[v]
                else:
                    # 숫자 인덱스로 변환 시도
                    try:
                        idx = int(v)
                        if 0 <= idx < len(options):
                            v = options[idx]  # 인덱스를 옵션 이름으로 변환
                        elif 1 <= idx <= len(options):
                            v = options[idx - 1]  # 1-based 인덱스
                    except (ValueError, TypeError):
                        pass
        
        # preserve_structure=True로 설정하여 템플릿에 있는 필드에만 값을 설정
        # 필드 키 추출과 동일한 키 집합을 유지하기 위해 템플릿 구조만 사용
        success = _set_value_in_nested(json_tpl[base_tag], field.json_path, v, preserve_structure=True)
        if success:
            success_count += 1
        else:
            fail_count += 1

    # 3) form.xml에서 값 merge
    # 중요: 템플릿 구조를 유지하면서 값만 채워넣습니다
    # 템플릿에 없는 경로는 추가하지 않고, 템플릿에 있는 경로에만 값을 설정합니다
    try:
        form_base_tag, form_values = _collect_form_field_values_from_pdf(pdf_path)
    except Exception as e:
        logger.error(f"form.xml 값 추출 중 오류 발생: {e}", exc_info=True)
        form_base_tag, form_values = None, {}
    
    if form_base_tag and form_values:
        if form_base_tag != base_tag:
            logger.warning(f"datasets base_tag={base_tag}, form base_tag={form_base_tag} 불일치")

        form_merge_count = 0
        form_merge_fail_count = 0
        for full_json_path, vals in form_values.items():
            try:
                # vals: list[str] (값이 없으면 빈 리스트)
                # 배열 인덱스 파싱: "Page1.KeepPageSeparate[0].FamilyMember" -> ["Page1", ("KeepPageSeparate", 0), "FamilyMember"]
                import re
                parts = []
                for part in full_json_path.split("."):
                    # 배열 인덱스 추출: "KeepPageSeparate[0]" -> ("KeepPageSeparate", 0)
                    match = re.match(r"^(.+)\[(\d+)\]$", part)
                    if match:
                        parts.append((match.group(1), int(match.group(2))))
                    else:
                        parts.append((part, -1))  # -1은 단일 값 의미
                
                if not parts:
                    continue
                if parts[0][0] != base_tag:
                    # base_tag 다르면 일단 스킵
                    continue

                # base_tag 제거하고 나머지 경로 사용
                tag_parts = parts[1:]  # 예: [("Page1", -1), ("KeepPageSeparate", 0), ("FamilyMember", -1), ("OptionsQ2", -1)]
                if not tag_parts:
                    continue

                # 리스트 or 단일값 공통 처리
                if not isinstance(vals, list):
                    vals = [vals] if vals else []

                # tag_parts에서 JSON 경로 생성 (배열 인덱스 포함)
                # 예: [("Page1", -1), ("KeepPageSeparate", 0), ("FamilyMember", -1), ("OptionsQ2", -1)]
                # -> [(Page1, -1), (KeepPageSeparate, 0), (FamilyMember, -1), (OptionsQ2, -1)]
                json_path = [(tag, idx) for tag, idx in tag_parts]
                
                # 템플릿 구조를 유지하면서 값만 설정
                # preserve_structure=True로 설정하여 템플릿에 없는 경로는 추가하지 않음
                # 값이 없는 경우: datasets.xml의 값을 유지하기 위해 스킵 (덮어쓰지 않음)
                if not vals:
                    continue
                # 값이 1개일 때
                elif len(vals) == 1:
                    # preserve_structure=True로 설정하여 템플릿에 있는 필드에만 값을 설정
                    # 필드 키 추출과 동일한 키 집합을 유지하기 위해 템플릿 구조만 사용
                    success = _set_value_in_nested(json_tpl[base_tag], json_path, vals[0], preserve_structure=True)
                    if success:
                        form_merge_count += 1
                    else:
                        form_merge_fail_count += 1
                else:
                    # 여러 개일 때는 템플릿 구조에 맞게 처리
                    # 템플릿에서 마지막 태그가 배열인지 확인
                    if json_path:
                        *prefix_path, (last_tag, last_idx) = json_path
                        # 템플릿에서 마지막 태그의 구조 확인
                        prefix_obj = json_tpl[base_tag]
                        for tag, idx in prefix_path:
                            if idx >= 0:
                                if isinstance(prefix_obj, list) and idx < len(prefix_obj):
                                    prefix_obj = prefix_obj[idx]
                                else:
                                    prefix_obj = None
                                    break
                            else:
                                if isinstance(prefix_obj, dict) and tag in prefix_obj:
                                    prefix_obj = prefix_obj[tag]
                                else:
                                    prefix_obj = None
                                    break
                        
                        # 마지막 태그가 배열인 경우에만 배열로 처리
                        if isinstance(prefix_obj, dict) and last_tag in prefix_obj:
                            if isinstance(prefix_obj[last_tag], list):
                                # 템플릿에 배열이 있으면 각 인덱스에 값 설정 (템플릿 크기 유지)
                                for idx, v in enumerate(vals):
                                    if idx < len(prefix_obj[last_tag]):
                                        current_path = prefix_path + [(last_tag, idx)]
                                        _set_value_in_nested(json_tpl[base_tag], current_path, v, preserve_structure=True)
                                form_merge_count += 1
                            else:
                                # 템플릿에 배열이 없으면 단일 값으로 처리 (첫 번째 값만 사용)
                                success = _set_value_in_nested(json_tpl[base_tag], json_path, vals[0], preserve_structure=True)
                                if success:
                                    form_merge_count += 1
                                else:
                                    form_merge_fail_count += 1
                        else:
                            # 템플릿 구조를 찾을 수 없으면 첫 번째 값만 사용
                            success = _set_value_in_nested(json_tpl[base_tag], json_path, vals[0], preserve_structure=True)
                            if success:
                                form_merge_count += 1
                            else:
                                form_merge_fail_count += 1
                    else:
                        # json_path가 비어있으면 스킵
                        logger.warning(f"json_path가 비어있음: full_json_path={full_json_path}")
                        form_merge_fail_count += 1
            except Exception as e:
                logger.error(f"form.xml 값 merge 중 오류 발생: full_json_path={full_json_path}, vals={vals}, error={e}", exc_info=True)
                form_merge_fail_count += 1
                continue
    return json_tpl

async def upload_and_extract(filename: str, contents: bytes) -> Dict[str, Any]:
    # 파일 검증
    _validate_pdf_file(filename, contents)
    
    base_dir = _get_base_dir()
    upload_dir = base_dir / "uploads"
    upload_dir.mkdir(exist_ok=True)
    
    file_path = upload_dir / filename
    form_name = file_path.stem
    
    should_use_existing = _is_file_identical(file_path, contents)
    
    try:
        if not should_use_existing:
            # 새 파일 저장
            with open(file_path, "wb") as f:
                f.write(contents)
        
        # ---- 여기서부터는 파일이 있다고 가정 ----
        # 스키마 추출 (빈 문자열로 채워진 템플릿)
        fields_json = extract_fields_from_pdf(file_path)
        
        # 최종 응답: 빈 문자열로 채워진 필드 구조만 반환 (extract_field_values와 동일한 형식)
        return fields_json
    
    except HTTPException:
        raise
    except Exception as e:
        if (not should_use_existing) and file_path.exists():
            file_path.unlink()
        logger.error(f"파일 처리 중 오류: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"파일 처리 중 오류가 발생했습니다: {str(e)}"
        )
def _collect_form_field_values_from_pdf(pdf_path: Path) -> tuple[str | None, Dict[str, list[str]]]:
    """
    XFA form 스트림에서 <field name="..."><value><text>...</text> 형태의 값을 수집해서
    JSON path (base_tag 포함) -> [value1, value2, ...] 딕셔너리로 반환.
    
    같은 경로가 여러 번 나오면 배열 인덱스를 포함한 경로를 생성합니다.
    예: 
    - 첫 번째: "IMM_0800.Page1.KeepPageSeparate[0].FamilyMember.OptionsQ2"
    - 두 번째: "IMM_0800.Page1.KeepPageSeparate[1].FamilyMember.OptionsQ2"

    예: "IMM_0800.Page1.TRdocuments.RadioButtonList": ["1", "3"]
    """
    form_bytes = _read_xfa_part_from_pdf(pdf_path, "form")
    if not form_bytes:
        return None, {}

    try:
        root = LET.fromstring(form_bytes)
    except Exception as e:
        logger.warning(f"form XML 파싱 실패: {e}")
        return None, {}

    # 기본 base_tag: 최상위 subform name (예: IMM_0800)
    base_sub = None
    base_tag = None
    for sf in root.findall(".//{*}subform"):
        name = sf.get("name")
        if name:
            base_sub = sf
            base_tag = name
            break

    if base_sub is None or base_tag is None:
        return None, {}

    # _collect_form_field_paths_from_pdf와 동일한 방식으로 경로 수집
    # 먼저 모든 경로를 수집 (값 추출용)
    all_path_tuples: List[tuple] = []
    
    def collect_paths(node: LET._Element, path_segments: List[str]):
        """모든 경로를 먼저 수집 (값 추출용)"""
        for child in node:
            if not isinstance(child.tag, str):
                continue
            # xfa:dataNode="dataGroup" 속성을 가진 노드나 그 자식은 제외
            if _has_data_group_ancestor(child):
                continue
            lname = LET.QName(child).localname

            if lname == "subform":
                name = child.get("name")
                if name:
                    collect_paths(child, path_segments + [name])
                else:
                    collect_paths(child, path_segments)
            elif lname == "exclGroup":
                gname = child.get("name")
                if gname:
                    if path_segments:
                        # base_tag 제거하고 경로 튜플 생성
                        path_tuple = tuple(path_segments[1:] + [gname]) if len(path_segments) > 1 else (gname,)
                    else:
                        path_tuple = (gname,)
                    all_path_tuples.append(path_tuple)
            elif lname == "field":
                fname = child.get("name")
                if fname:
                    # 버튼 필드 제외 (SaveButton, ResetButton, PrintButton)
                    if any(btn in fname for btn in ["SaveButton", "ResetButton", "PrintButton"]):
                        continue
                    if path_segments:
                        # base_tag 제거하고 경로 튜플 생성
                        path_tuple = tuple(path_segments[1:] + [fname]) if len(path_segments) > 1 else (fname,)
                    else:
                        path_tuple = (fname,)
                    all_path_tuples.append(path_tuple)
            else:
                collect_paths(child, path_segments)
    
    # 모든 경로 수집
    collect_paths(base_sub, [base_tag])
    
    # _build_field_template과 동일한 방식으로 접두사 카운트
    # 각 경로 접두사가 여러 번 나오는지 카운트
    prefix_count: Dict[tuple, int] = {}
    for path_tuple in all_path_tuples:
        for i in range(1, len(path_tuple) + 1):
            prefix = tuple(path_tuple[:i])
            prefix_count[prefix] = prefix_count.get(prefix, 0) + 1
    
    # 같은 경로가 여러 번 나오는지 카운트
    path_count: Dict[tuple, int] = {}
    for path_tuple in all_path_tuples:
        path_count[path_tuple] = path_count.get(path_tuple, 0) + 1
    
    results: Dict[str, list[str]] = {}
    # 같은 경로가 나온 횟수를 추적
    seen_paths: Dict[tuple, int] = {}
    
    def build_path_with_array_indices(path_segments: List[str], field_name: str) -> str:
        """
        경로에 배열 인덱스를 추가하여 full_json_path 생성
        _build_field_template과 동일한 로직 사용
        """
        if not path_segments:
            return field_name
        
        # base_tag 제거하고 경로 튜플 생성
        path_tuple = tuple(path_segments[1:] + [field_name]) if len(path_segments) > 1 else (field_name,)
        
        # 같은 경로가 여러 번 나오는지 확인
        if path_tuple not in seen_paths:
            seen_paths[path_tuple] = 0
        else:
            seen_paths[path_tuple] += 1
        current_idx = seen_paths[path_tuple]
        
        # _build_field_template과 동일한 로직 사용
        count = path_count.get(path_tuple, 1)
        
        if count > 1:
            # 같은 경로가 여러 번 나오면 배열로 처리
            path_with_indices = []
            array_idx_added = False
            
            for i, tag in enumerate(path_tuple):
                # 이전 경로까지의 접두사
                prev_prefix = tuple(path_tuple[:i])
                # 현재 태그를 포함한 접두사
                current_prefix = tuple(path_tuple[:i+1])
                
                # 이전 접두사가 한 번만 나오고, 현재 접두사가 여러 번 나오면
                # 현재 태그에 배열 인덱스 추가 (가장 짧은 공통 접두사)
                prev_cnt = prefix_count.get(prev_prefix, 0)
                current_cnt = prefix_count.get(current_prefix, 0)
                
                if prev_cnt == 1 and current_cnt > 1 and not array_idx_added:
                    # 현재 태그가 반복되는 첫 번째 위치
                    path_with_indices.append(f"{tag}[{current_idx}]")
                    array_idx_added = True
                elif i == len(path_tuple) - 1 and not array_idx_added:
                    # 마지막 태그이고 아직 배열 인덱스를 추가하지 않았으면
                    # (전체 경로가 반복되는 경우 - fallback)
                    path_with_indices.append(f"{tag}[{current_idx}]")
                else:
                    path_with_indices.append(tag)
        else:
            # 단일 값으로 처리
            path_with_indices = list(path_tuple)
        
        return f"{base_tag}." + ".".join(path_with_indices)

    def walk(node: LET._Element, path_segments: List[str]):
        for child in node:
            if not isinstance(child.tag, str):
                continue
            # xfa:dataNode="dataGroup" 속성을 가진 노드나 그 자식은 제외
            if _has_data_group_ancestor(child):
                continue
            lname = LET.QName(child).localname

            if lname == "subform":
                name = child.get("name")
                if name:
                    walk(child, path_segments + [name])
                else:
                    walk(child, path_segments)
            elif lname == "exclGroup":
                # exclGroup은 라디오 버튼 그룹으로, 그 자체가 필드입니다
                gname = child.get("name")
                if gname:
                    # path_segments = [IMM_0800, Page1, TRdocuments, ...]
                    if path_segments:
                        full_json_path = build_path_with_array_indices(path_segments, gname)
                    else:
                        full_json_path = gname
                    
                    # exclGroup의 값은 내부의 선택된 field에서 찾습니다
                    # 라디오 버튼의 경우, 선택된 옵션의 필드를 찾아서 그 필드의 이름을 반환합니다
                    val = None
                    # 모든 필드를 확인하여 선택된 옵션 찾기
                    for field in child.findall(".//{*}field"):
                        field_name = field.get("name")
                        if field_name:
                            text_el = field.find(".//{*}value/{*}text")
                            if text_el is not None:
                                # xsi:nil="true" 속성이 있으면 선택되지 않음
                                if text_el.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
                                    continue
                                
                                field_val = (text_el.text or "").strip()
                                
                                # 라디오 버튼의 경우, 선택된 옵션 판단:
                                # - 값이 "1" 또는 "Y"이면 선택됨
                                # - 값이 비어있지 않고 "0"이 아니면 선택된 것으로 간주
                                #   (예: "N" 값이 있으면 해당 필드가 선택된 것, "2", "3" 등도 선택된 것)
                                # - 값이 비어있거나 "0"이면 선택되지 않음
                                if field_val in ("1", "Y"):
                                    val = field_name
                                    break
                                elif field_val and field_val != "0":
                                    val = field_name
                                    break
                    
                    if val:
                        # 값이 있는 경우: 리스트로 누적
                        if full_json_path not in results:
                            results[full_json_path] = [val]
                        else:
                            results[full_json_path].append(val)
                    else:
                        # 빈 리스트로 추가하여 필드 경로는 유지 (나중에 datasets.xml 값으로 채울 수 있음)
                        if full_json_path not in results:
                            results[full_json_path] = []
                    # exclGroup 내부의 field들(No, Yes 등)은 별도 필드가 아니므로 재귀하지 않음
                    # exclGroup 자체만 필드로 취급
                # exclGroup 내부는 처리하지 않음 (라디오 버튼 옵션은 별도 필드가 아님)
            elif lname == "field":
                fname = child.get("name")
                if not fname:
                    continue
                
                # 버튼 필드 제외 (SaveButton, ResetButton, PrintButton)
                if any(btn in fname for btn in ["SaveButton", "ResetButton", "PrintButton"]):
                    continue
                
                # path_segments = [IMM_0800, Page1, TRdocuments, ...]
                if path_segments:
                    full_json_path = build_path_with_array_indices(path_segments, fname)
                else:
                    full_json_path = fname
                
                # 값 추출 (값이 없어도 필드 경로는 수집)
                text_el = child.find(".//{*}value/{*}text")
                if text_el is not None:
                    # xsi:nil="true" 속성 확인
                    is_nil = text_el.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true"
                    if is_nil:
                        # nil이면 빈 값으로 처리
                        val = ""
                    else:
                        val = (text_el.text or "").strip()
                    
                    if val:
                        # 값이 있는 경우: 리스트로 누적
                        if full_json_path not in results:
                            results[full_json_path] = [val]
                        else:
                            results[full_json_path].append(val)
                    else:
                        # 값이 없는 경우: 빈 리스트로 표시 (필드 경로는 포함)
                        if full_json_path not in results:
                            results[full_json_path] = []
                else:
                    # value/text 요소가 없는 경우: 빈 리스트로 표시 (필드 경로는 포함)
                    if full_json_path not in results:
                        results[full_json_path] = []
            else:
                walk(child, path_segments)

    # 시작 path: [base_tag]
    walk(base_sub, [base_tag])

    return base_tag, results