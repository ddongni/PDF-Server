from __future__ import annotations
from pathlib import Path
from lxml import etree

# 직접 실행 시와 모듈로 실행 시 모두 지원
try:
    from .utils import (
        read_datasets_from_pdf, write_datasets_to_pdf,
        parse_xml, serialize_xml,
        set_node, NS
    )
except ImportError:
    # 직접 실행 시 (python app/utils/pdf_filler.py) - 같은 디렉토리의 utils.py 사용
    import utils
    read_datasets_from_pdf = utils.read_datasets_from_pdf
    write_datasets_to_pdf = utils.write_datasets_to_pdf
    parse_xml = utils.parse_xml
    serialize_xml = utils.serialize_xml
    set_node = utils.set_node
    NS = utils.NS

def _find_base_form_node(root: etree._Element) -> tuple[etree._Element, str]:
    """XFA XML 루트에서 베이스 폼 노드를 찾습니다."""
    data_hits = root.xpath(".//xfa:data", namespaces=NS)
    if data_hits and len(data_hits[0]):
        el = data_hits[0][0]
        from lxml.etree import QName
        return el, QName(el).localname
    from lxml.etree import QName
    return root, QName(root).localname

def _json_path_to_xfa_path(json_path: str, base_tag: str) -> str:
    """JSON 경로를 XFA 상대 경로로 변환합니다.
    
    예: 
    - "IMM_0800.Page1.PersonalDetails.Name.FamilyName" -> "./Page1/PersonalDetails/Name/FamilyName"
    - "IMM_0800.items[0].name" -> "./items[1]/name" (XFA는 1-based)
    """
    # base_tag 제거
    if json_path.startswith(base_tag + "."):
        rel_path = json_path[len(base_tag) + 1:]
    elif json_path == base_tag:
        return "./"
    else:
        rel_path = json_path
    
    if not rel_path:
        return "./"
    
    # 배열 인덱스 처리: [0] -> [1] (XFA는 1-based)
    import re
    def replace_index(match):
        idx = int(match.group(1))
        return f"[{idx + 1}]"  # 0-based -> 1-based
    
    rel_path = re.sub(r'\[(\d+)\]', replace_index, rel_path)
    
    # 점을 슬래시로 변환하고 ./ 접두사 추가
    return "./" + rel_path.replace(".", "/")

def _traverse_json_to_xfa(form: etree._Element, data: dict, base_tag: str, current_path: str = ""):
    """JSON 구조를 재귀적으로 순회하며 XFA 폼에 값을 설정합니다."""
    for key, value in data.items():
        # 현재 경로 구성
        if current_path:
            json_path = f"{current_path}.{key}"
        else:
            json_path = key
        
        # base_tag가 있으면 건너뛰기 (최상위 루트)
        if json_path == base_tag:
            # base_tag 내부로 재귀
            if isinstance(value, dict):
                _traverse_json_to_xfa(form, value, base_tag, "")
            continue
        
        if isinstance(value, dict):
            # 중첩된 딕셔너리: 재귀 호출
            _traverse_json_to_xfa(form, value, base_tag, json_path)
        elif isinstance(value, list):
            # 배열: 각 요소 처리
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    _traverse_json_to_xfa(form, item, base_tag, f"{json_path}[{i}]")
                else:
                    # 배열의 리프 값
                    xfa_path = _json_path_to_xfa_path(f"{json_path}[{i}]", base_tag)
                    set_node(form, xfa_path, "" if item is None else str(item))
        else:
            # 리프 노드: XFA 경로로 변환하여 설정
            xfa_path = _json_path_to_xfa_path(json_path, base_tag)
            out = "" if value is None else str(value)
            set_node(form, xfa_path, out)

def _set_form_from_json(root: etree._Element, data: dict, base_tag_hint: str | None = None):
    """JSON 데이터를 XFA 폼에 채웁니다. FIELD_MAP 없이 JSON 구조를 직접 사용합니다."""
    form, auto_base = _find_base_form_node(root)
    base_tag = base_tag_hint or auto_base
    
    # data가 {base_tag: {...}} 형태인지 확인
    if base_tag in data:
        target_data = data[base_tag]
    else:
        # base_tag가 없으면 data 자체가 base_tag 내부 데이터
        target_data = data
    
    # JSON 구조를 순회하며 XFA에 매핑
    _traverse_json_to_xfa(form, target_data, base_tag)

def _get_base_tag_from_json(data: dict) -> str | None:
    """JSON 데이터에서 base_tag를 추론합니다."""
    # JSON의 최상위 키를 base_tag로 사용
    if len(data) == 1:
        return next(iter(data.keys()))
    # 여러 키가 있으면 첫 번째 키를 반환
    return next(iter(data.keys()), None)

def _fill_pdf(template_pdf: str | Path, data: dict, out_pdf: str | Path, base_tag_hint: str | None = None):
    """PDF 폼을 데이터로 채웁니다.
    
    Args:
        template_pdf: 입력 PDF 파일 경로
        data: 채울 데이터 (dict)
        out_pdf: 출력 PDF 파일 경로
        base_tag_hint: 베이스 태그 힌트 (선택사항, 자동 감지 가능)
    """
    datasets_xml = read_datasets_from_pdf(template_pdf)
    root = parse_xml(datasets_xml)
    _set_form_from_json(root, data, base_tag_hint=base_tag_hint)
    new_xml = serialize_xml(root)
    write_datasets_to_pdf(template_pdf, new_xml, out_pdf)

def process_input_json(json_path: Path, pdfs_dir: Path, output_dir: Path) -> bool:
    """단일 JSON 파일을 처리합니다."""
    form_name = json_path.stem  # 예: "IMM0800e"
    
    # PDF 파일 찾기
    pdf_file = pdfs_dir / f"{form_name}.pdf"
    if not pdf_file.exists():
        # 대소문자 무시해서 찾기
        pdf_files = list(pdfs_dir.glob(f"{form_name.lower()}.pdf"))
        pdf_files.extend(list(pdfs_dir.glob(f"{form_name.upper()}.pdf")))
        if pdf_files:
            pdf_file = pdf_files[0]
        else:
            print(f"❌ {form_name}: PDF 파일을 찾을 수 없습니다: {pdf_file}")
            return False
    
    try:
        # JSON 데이터 로드
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # base_tag 추론
        base_tag = get_base_tag_from_json(data)
        print(f"✅ {form_name}: JSON 로드 완료 (base={base_tag})")
        
        # 출력 파일 경로
        output_file = output_dir / f"{form_name}.pdf"
        output_dir.mkdir(exist_ok=True)
        
        # PDF 채우기
        fill_pdf(pdf_file, data, output_file, base_tag_hint=base_tag)
        print(f"✅ {form_name}: PDF 생성 완료 → {output_file}")
        return True
        
    except Exception as e:
        print(f"❌ {form_name}: 오류 발생 - {e}")
        import traceback
        traceback.print_exc()
        return False

def process_all_inputs():
    """input 폴더의 모든 JSON 파일을 처리합니다."""
    base_dir = Path(__file__).parent.parent
    input_dir = base_dir / "input"
    pdfs_dir = base_dir / "pdfs"
    output_dir = base_dir / "output"
    
    if not input_dir.exists():
        print(f"❌ input 폴더가 없습니다: {input_dir}")
        return
    
    if not pdfs_dir.exists():
        print(f"❌ pdfs 폴더가 없습니다: {pdfs_dir}")
        return
    
    json_files = sorted(input_dir.glob("*.json"))
    if not json_files:
        print(f"❌ input 폴더에 JSON 파일이 없습니다: {input_dir}")
        return
    
    print(f"📁 {len(json_files)}개의 JSON 파일을 처리합니다...\n")
    
    success_count = 0
    for json_file in json_files:
        print(f"처리 중: {json_file.name}")
        if process_input_json(json_file, pdfs_dir, output_dir):
            success_count += 1
        print()
    
    print(f"✅ 완료: {success_count}/{len(json_files)}개 파일 처리 성공")

# CLI 실행
if __name__ == "__main__":
    import sys
    import json
    
    # 인자가 없으면 input 폴더 일괄 처리
    if len(sys.argv) == 1:
        process_all_inputs()
        sys.exit(0)
    
    # 인자가 3개면 단일 파일 처리
    if len(sys.argv) == 4:
        inp, js, outp = sys.argv[1:4]
    else:
        print("Usage:")
        print("  # input 폴더 일괄 처리:")
        print("  python -m app.utils.pdf_filler")
        print("\n  # 단일 파일 처리:")
        print("  python -m app.utils.pdf_filler <input.pdf> <data.json> <output.pdf>")
        print("\n예시:")
        print("  python -m app.utils.pdf_filler")
        print("  python -m app.utils.pdf_filler app/pdfs/IMM0800e.pdf app/input/IMM0800e.json app/output/IMM0800e.pdf")
        sys.exit(1)
    
    try:
        # JSON 데이터 로드
        with open(js, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # base_tag 자동 추론
        base_tag = _get_base_tag_from_json(data)
        
        print(f"✅ JSON 로드 완료 (base={base_tag})")
        
        # PDF 채우기
        _fill_pdf(inp, data, outp, base_tag_hint=base_tag)
        print(f"✅ PDF 생성 완료 → {outp}")
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}", file=sys.stderr)
        sys.exit(1)

