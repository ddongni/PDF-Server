from __future__ import annotations
import json, re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
from lxml import etree as LET

try:
    from .utils import read_datasets_from_pdf, parse_xml, strip_ns
except ImportError:
    from utils import read_datasets_from_pdf, parse_xml, strip_ns

# ============== 환경 설정 ==============
INPUT_DIR = Path(__file__).parent.parent / "pdfs"  # PDF가 있는 폴더

# ============== XML 유틸 ==============
def _find_base_form_node(xml_bytes: bytes) -> tuple[LET._Element, str]:
    root = parse_xml(xml_bytes)

    # data 노드 찾기 (find → xpath)
    data_nodes = root.xpath("//*[local-name()='data']")
    data_node = data_nodes[0] if data_nodes else None

    if data_node is not None:
        children = [c for c in data_node if isinstance(c.tag, str)]
        if children:
            return children[0], strip_ns(children[0].tag)

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
    """
    path: [(tag, idx), ...]
    idx=-1이면 단일노드, idx>=0이면 배열
    leaf는 "" 기본값
    """
    cur = obj
    for i, (tag, idx) in enumerate(path):
        is_leaf = (i == len(path) - 1)
        if idx >= 0:
            cur.setdefault(tag, [])
            arr = cur[tag]
            while len(arr) <= idx:
                arr.append({})
            if is_leaf:
                if isinstance(arr[idx], dict):
                    arr[idx] = ""
            else:
                if isinstance(arr[idx], str):
                    arr[idx] = {}
                cur = arr[idx]
        else:
            if is_leaf:
                cur.setdefault(tag, "")
            else:
                cur.setdefault(tag, {})
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
    return not any(isinstance(c.tag, str) for c in el)

def _collect_leaf_fields(base: LET._Element) -> List[Field]:
    fields: List[Field] = []
    for el in base.iter():
        if not isinstance(el.tag, str):
            continue
        if is_leaf(el):
            rx = xpath_from_to(el, base)
            jp = path_with_index(el, base)
            key = ".".join([f"{t}[{i}]" if i >= 0 else t for t, i in jp])
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
        set_in_nested(tpl, f.json_path)
    return {base_tag: tpl}

# ============== 메인 파이프라인 ==============
def process_one_pdf(pdf_path: Path) -> None:
    # field_maps 디렉토리 생성
    field_maps_dir = Path(__file__).parent.parent / "field_maps"
    field_maps_dir.mkdir(exist_ok=True)

    # 1) datasets.xml 추출
    xml_bytes = read_datasets_from_pdf(pdf_path)

    # 2) 베이스 폼 탐색 + leaf 필드 수집
    base_node, base_tag = _find_base_form_node(xml_bytes)
    fields = _collect_leaf_fields(base_node)

    form_name = pdf_path.stem

    # 3) JSON 템플릿 저장 (field_maps에 저장)
    json_tpl = _build_json_template(base_tag, fields)
    json_file = field_maps_dir / f"{form_name}.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(json_tpl, f, ensure_ascii=False, indent=2)

    print(f"✅ {pdf_path.name} → field_maps/{form_name}.json 생성 완료 (base={base_tag}, {len(fields)}개 필드)")


def main():
    pdfs = sorted(p for p in INPUT_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")
    if not pdfs:
        print("PDF 파일이 없습니다.")
        return
    for p in pdfs:
        try:
            process_one_pdf(p)
        except Exception as e:
            print(f"❌ 실패: {p.name} - {e}")

if __name__ == "__main__":
    main()