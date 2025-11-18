"""PDF 필드 채우기 서비스"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple
from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.utils.utils import (
    read_datasets_from_pdf,
    write_datasets_to_pdf,
    parse_xml,
    serialize_xml,
    strip_ns
)
from app.services.pdf_extract_service import _find_base_form_node
from lxml import etree

import os

logger = logging.getLogger(__name__)


def _set_or_create_node(base_node: etree._Element, path_parts: List[str], value: str):
    """노드를 찾아서 값을 설정하고, 없으면 생성합니다.
    
    Args:
        base_node: 시작 노드 (예: IMM_0800)
        path_parts: 경로 부분 리스트 (배열 인덱스 포함, 예: ["Page1", "KeepPageSeparate", "[0]", "FamilyMember"])
        value: 설정할 값
    """
    # 플레이스홀더 값 처리: *로 시작하는 값은 빈 문자열로 처리
    if value and value.strip().startswith("*"):
        value = ""
    
    cur = base_node
    parent_node = None  # 라디오 버튼 처리를 위한 부모 노드 추적
    i = 0
    
    while i < len(path_parts):
        part = path_parts[i]
        
        # 배열 인덱스는 건너뛰기 (태그 처리 시 함께 처리)
        if part.startswith("[") and part.endswith("]"):
            i += 1
            continue
        
        # 태그 이름
        tag_name = part
        
        # 다음 부분이 배열 인덱스인지 확인
        array_idx = None
        if i + 1 < len(path_parts) and path_parts[i + 1].startswith("[") and path_parts[i + 1].endswith("]"):
            array_idx = int(path_parts[i + 1][1:-1])  # 0-based
            i += 2  # 태그와 인덱스 모두 처리
        else:
            i += 1  # 태그만 처리
        
        # 자식 노드 찾기
        children = [c for c in cur if strip_ns(c.tag) == tag_name]
        
        # 라디오 버튼 처리를 위해 부모 노드 저장 (마지막 두 부분이 같을 때 사용)
        # 경로의 마지막 두 부분이 같으면, 첫 번째 노드를 라디오 버튼 그룹으로 간주
        if len(path_parts) >= 2 and path_parts[-2] == path_parts[-1]:
            # 현재 처리 중인 부분이 마지막에서 두 번째 부분이면 부모 노드로 저장
            # i는 이미 증가했으므로, 남은 경로가 1개면 마지막 부분 직전
            remaining_count = len([p for p in path_parts[i:] if not (p.startswith("[") and p.endswith("]"))])
            if remaining_count == 1:
                parent_node = cur
        
        if array_idx is not None:
            # 배열 인덱스가 있으면 해당 인덱스의 노드 사용/생성
            while len(children) <= array_idx:
                new_node = etree.Element(tag_name)
                cur.append(new_node)
                children.append(new_node)
            cur = children[array_idx]
        else:
            # 배열 인덱스가 없으면 첫 번째 노드 사용/생성
            if children:
                cur = children[0]
            else:
                new_node = etree.Element(tag_name)
                cur.append(new_node)
                cur = new_node
    
    # 마지막 노드에 값 설정
    # XFA 특수 노드 처리: #value, #integer 등
    final_value = "" if value is None else str(value)
    
    # 라디오 버튼 처리: 경로의 마지막 두 부분이 같으면 (예: ["Sex", "Sex"]), 
    # 첫 번째 노드를 라디오 버튼 그룹으로 간주하고 그 아래에 옵션 필드를 찾아서 처리
    if final_value and len(path_parts) >= 2 and path_parts[-2] == path_parts[-1]:
        # 부모 노드가 저장되어 있으면 사용, 없으면 현재 노드의 부모 사용
        radio_group_node = parent_node if parent_node is not None else cur.getparent()
        
        if radio_group_node is not None:
            # 부모 노드(라디오 버튼 그룹)의 자식 노드들 중에서 값과 일치하는 옵션 필드 찾기
            child_nodes = [c for c in radio_group_node if isinstance(c.tag, str)]
            matched_child = None
            for child in child_nodes:
                child_tag = strip_ns(child.tag)
                if child_tag == final_value:
                    matched_child = child
                    break
            
            if matched_child:
                # 선택된 옵션은 "1" 또는 "Y"로 설정
                matched_child.text = "1"
                # 나머지 옵션들은 "0" 또는 빈 값으로 설정
                for child in child_nodes:
                    if child != matched_child:
                        child.text = ""
                return
    
    # 일반적인 라디오 버튼 처리: 현재 노드의 자식 노드들 중에서 값과 일치하는 옵션 필드를 찾아서 처리
    if final_value:
        # 현재 노드의 자식 노드들을 확인
        child_nodes = [c for c in cur if isinstance(c.tag, str)]
        # 자식 노드 중에서 값과 일치하는 노드 찾기 (태그 이름으로)
        matched_child = None
        for child in child_nodes:
            child_tag = strip_ns(child.tag)
            # 태그 이름이 값과 일치하는지 확인
            if child_tag == final_value:
                matched_child = child
                break
        
        # 일치하는 자식 노드를 찾았으면 라디오 버튼으로 처리
        if matched_child:
            # 선택된 옵션은 "1" 또는 "Y"로 설정
            matched_child.text = "1"
            # 나머지 옵션들은 "0" 또는 빈 값으로 설정
            for child in child_nodes:
                if child != matched_child:
                    child.text = ""
            return
    
    # #value 노드가 있으면 그 안의 #integer 또는 직접 텍스트에 설정
    value_nodes = [c for c in cur if strip_ns(c.tag) == "#value"]
    if value_nodes:
        value_node = value_nodes[0]
        # #integer 노드 찾기
        integer_nodes = [c for c in value_node if strip_ns(c.tag) == "#integer"]
        if integer_nodes:
            # #integer 노드에 숫자만 설정 (숫자가 아니면 빈 문자열)
            try:
                # 숫자로 변환 가능한지 확인
                if final_value:
                    num_value = float(final_value)
                    integer_nodes[0].text = str(int(num_value))
                else:
                    integer_nodes[0].text = ""
            except (ValueError, TypeError):
                # 숫자가 아니면 빈 문자열로 설정
                integer_nodes[0].text = ""
        else:
            # #integer가 없으면 #value 노드에 직접 설정
            value_node.text = final_value
    else:
        # #value 노드가 없으면 현재 노드에 직접 설정
        cur.text = final_value


def _build_json_path_with_indices(data: Any, current_path: List[str] = None) -> List[Tuple[List[str], Any]]:
    """JSON 데이터를 순회하면서 (경로, 값) 튜플 리스트를 생성합니다.
    배열 인덱스도 포함합니다.
    
    Returns:
        [(경로, 값), ...] 형태의 리스트
        경로는 ["IMM_0800", "Page1", "KeepPageSeparate", "[0]", "FamilyMember", ...] 형태
    """
    if current_path is None:
        current_path = []
    
    results = []
    
    if isinstance(data, dict):
        for key, value in data.items():
            new_path = current_path + [key]
            if isinstance(value, (dict, list)):
                results.extend(_build_json_path_with_indices(value, new_path))
            else:
                # 리프 노드
                results.append((new_path, value))
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            # 배열 인덱스를 경로에 추가
            new_path = current_path + [f"[{idx}]"]
            if isinstance(item, (dict, list)):
                results.extend(_build_json_path_with_indices(item, new_path))
            else:
                # 리프 노드
                results.append((new_path, item))
    else:
        # 리프 노드 (문자열, 숫자 등)
        results.append((current_path, data))
    
    return results


def _json_path_to_xpath(json_path: List[str], base_tag: str) -> str:
    """JSON 경로를 XPath로 변환합니다.
    
    Args:
        json_path: JSON 경로 리스트 (base_tag 제외, 배열 인덱스 포함)
        base_tag: base 태그 (예: "IMM_0800")
    
    Returns:
        XPath 문자열 (예: "./Page1/ApplyFor/CheckBox1" 또는 "./Page1/KeepPageSeparate[1]/FamilyMember")
    
    예:
        ["Page1", "ApplyFor", "CheckBox1"] -> "./Page1/ApplyFor/CheckBox1"
        ["Page1", "KeepPageSeparate", "[0]", "FamilyMember"] -> "./Page1/KeepPageSeparate[1]/FamilyMember"
    """
    if not json_path:
        return f"./{base_tag}"
    
    xpath_parts = []
    
    for part in json_path:
        if part.startswith("[") and part.endswith("]"):
            # 배열 인덱스는 이전 경로에 추가 (1-based로 변환)
            if xpath_parts:
                idx = int(part[1:-1])
                xpath_parts[-1] = f"{xpath_parts[-1]}[{idx + 1}]"
        else:
            xpath_parts.append(part)
    
    return "./" + "/".join(xpath_parts)


def fill_pdf_with_data(
    filename: str,
    fields: Dict[str, Any],
    background_tasks: Any = None
) -> FileResponse:
    """JSON 데이터를 사용하여 PDF 필드를 채웁니다.
    
    Args:
        filename: PDF 파일명
        fields: 필드 데이터 (JSON 형식)
        background_tasks: FastAPI BackgroundTasks (선택사항)
    
    Returns:
        채워진 PDF 파일 응답
    """
    # 파일 경로 확인
    base_dir = Path(__file__).parent.parent.parent
    upload_dir = base_dir / "uploads"
    pdf_path = upload_dir / filename
    
    if not pdf_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"파일 '{filename}'을 찾을 수 없습니다."
        )
    
    try:
        # 1) datasets.xml 읽기 및 base 노드 찾기
        datasets_bytes = read_datasets_from_pdf(pdf_path)
        datasets_root = parse_xml(datasets_bytes)
        
        # base_node를 datasets_root에서 직접 찾기 (같은 트리에서)
        _, base_tag = _find_base_form_node(datasets_bytes)
        
        if not base_tag:
            raise ValueError("datasets.xml에서 base 태그를 찾을 수 없습니다.")
        
        # datasets_root에서 base_node 찾기
        base_node = None
        # data 노드 우선 확인
        data_nodes = datasets_root.xpath("//*[local-name()='data']")
        if data_nodes and len(data_nodes) > 0:
            data_node = data_nodes[0]
            children = [c for c in data_node if isinstance(c.tag, str)]
            if children and strip_ns(children[0].tag) == base_tag:
                base_node = children[0]
        
        # data 노드에서 못 찾으면 form 노드 확인
        if base_node is None:
            form_nodes = datasets_root.xpath("//*[local-name()='form']")
            if form_nodes and strip_ns(form_nodes[0].tag) == base_tag:
                base_node = form_nodes[0]
        
        # 그것도 없으면 루트의 첫 번째 자식 확인
        if base_node is None:
            for child in datasets_root:
                if isinstance(child.tag, str) and strip_ns(child.tag) == base_tag:
                    base_node = child
                    break
        
        if base_node is None:
            raise ValueError(f"datasets.xml에서 '{base_tag}' 노드를 찾을 수 없습니다.")
        
        # 2) JSON 데이터를 순회하면서 XPath 생성하고 값 설정
        json_paths = _build_json_path_with_indices(fields)
        
        success_count = 0
        fail_count = 0
        
        for json_path, value in json_paths:
            try:
                # base_tag 확인 및 제거
                if not json_path:
                    continue
                
                # base_tag 확인: JSON의 첫 번째 키가 base_tag와 일치해야 함
                # 하지만 JSON에는 실제 폼 태그(IMM_0800)가 있고, datasets.xml에는 data 노드 아래에 있을 수 있음
                # 따라서 JSON의 첫 번째 키를 그대로 사용
                json_base_tag = json_path[0] if json_path else None
                if not json_base_tag:
                    continue
                
                # JSON의 첫 번째 키(base_tag) 제거
                # base_node는 이미 실제 데이터 노드(IMM_0800)이므로 JSON의 base_tag만 제거
                json_path_without_base = json_path[1:]
                
                if not json_path_without_base:
                    continue
                
                # JSON 경로를 XPath로 변환
                xpath = _json_path_to_xpath(json_path_without_base, base_tag)
                
                # 값 설정
                str_value = "" if value is None else str(value)
                
                # set_node 호출 - 노드가 없으면 생성
                _set_or_create_node(base_node, json_path_without_base, str_value)
                success_count += 1
                
            except Exception as e:
                logger.warning(f"필드 설정 실패: 경로={json_path}, 값={value}, 오류={e}")
                fail_count += 1
        
        logger.info(f"PDF 필드 채우기 완료: 성공={success_count}, 실패={fail_count}")
        
        # 3) datasets.xml을 PDF에 저장
        updated_datasets = serialize_xml(datasets_root)
        
        output_path = upload_dir / f"filled_{filename}"
        write_datasets_to_pdf(pdf_path, updated_datasets, output_path)

        if background_tasks:
            background_tasks.add_task(os.remove, output_path)

        return FileResponse(
            path=str(output_path),
            filename=f"filled_{filename}",
            media_type="application/pdf"
        )
        
    except Exception as e:
        logger.error(f"PDF 필드 채우기 중 오류: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"PDF 필드 채우기 중 오류가 발생했습니다: {str(e)}"
        )

