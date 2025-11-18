from __future__ import annotations
import logging
import tempfile
from pathlib import Path
from typing import Dict, Any, Tuple, List
from lxml import etree as LET

from fastapi import HTTPException, BackgroundTasks
from fastapi.responses import FileResponse

from app.utils.utils import (
    read_datasets_from_pdf, write_datasets_to_pdf,
    read_template_from_pdf, write_template_to_pdf,
    parse_xml, serialize_xml,
    set_node, NS, strip_ns
)

import re

from app.services.pdf_extract_service import (
    _find_base_form_node
)

from app.services.pdf_field_type_service import (
    extract_field_types_with_path_map
)

logger = logging.getLogger(__name__)

def _key_exists_in_template(template: dict, base_tag: str, json_path: List[Tuple[str, int]]) -> bool:
    """템플릿에 해당 경로가 존재하는지 확인합니다."""
    if base_tag not in template:
        return False
    
    cur = template[base_tag]
    for tag, idx in json_path:
        if isinstance(cur, dict):
            if tag not in cur:
                return False
            cur = cur[tag]
            # 배열인 경우 인덱스 확인
            if isinstance(cur, list) and idx >= 0:
                if idx >= len(cur):
                    return False
                cur = cur[idx]
        elif isinstance(cur, list):
            if idx >= 0 and idx < len(cur):
                cur = cur[idx]
            else:
                return False
        else:
            return False
    return True

def _json_path_to_xfa_path(json_path: str, base_tag: str, field_xpath_map: Dict[str, str] = None) -> str:
    """JSON 경로를 XFA 상대 경로로 변환합니다.
    
    Args:
        json_path: JSON 경로 (예: "IMM_0800.Page1.PersonalDetails.Name.FamilyName")
        base_tag: 베이스 태그 (예: "IMM_0800")
        field_xpath_map: JSON 경로 -> XFA 경로 매핑 (선택사항, 있으면 우선 사용)
    
    Returns:
        XFA 상대 경로 (예: "./Page1/PersonalDetails/Name/FamilyName")
    """
    # 매핑이 있으면 우선 사용
    if field_xpath_map and json_path in field_xpath_map:
        return field_xpath_map[json_path]
    
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

def _convert_value_for_field(value: str, field_type_info: Dict = None) -> str:
    """필드 타입에 따라 값을 변환합니다.
    
    Args:
        value: 원본 값
        field_type_info: 필드 타입 정보 (type, options, value_map 등)
    
    Returns:
        변환된 값
    """
    if not field_type_info or not value:
        return value
    
    field_type = field_type_info.get("type")
    options = field_type_info.get("options", [])
    value_map = field_type_info.get("value_map", {})
    
    # choiceList (radio) 필드의 경우, 값이 옵션 목록에 없으면 옵션 텍스트로 변환 시도
    if field_type == "radio" and options:
        # 값이 이미 옵션 목록에 있으면 그대로 사용
        if value in options:
            return value
        
        # value_map이 있으면 값-텍스트 매핑 사용
        if value_map and value in value_map:
            mapped_value = value_map[value]
            if mapped_value in options:
                return mapped_value
        
        # 일반적인 값 변환: "Y" -> "Yes", "N" -> "No"
        common_value_map = {"Y": "Yes", "N": "No", "1": "Yes", "0": "No"}
        if value in common_value_map and common_value_map[value] in options:
            return common_value_map[value]
        
        # 값이 옵션 목록에 없으면, 옵션 인덱스로 변환 시도
        # 예: "23" -> options[23] (인덱스 23번째 옵션)
        try:
            idx = int(value)
            if 1 <= idx <= len(options):  # 1-based 인덱스
                return options[idx - 1]
            elif 0 <= idx < len(options):  # 0-based 인덱스
                return options[idx]
        except (ValueError, TypeError):
            pass
        
        # 대소문자 무시 매칭 시도
        for opt in options:
            if opt.lower() == value.lower():
                return opt
        
        # 값이 옵션 목록에 없고 인덱스도 아니면 그대로 사용
        return value
    
    return value
def _find_matching_xpath(
    json_path: str,
    field_xpath_map: Dict[str, str],
    base_tag: str
) -> str | None:
    """
    JSON 경로에 대해 field_xpath_map에서 매칭되는 XFA 경로를 찾습니다.
    배열 인덱스가 포함된 경로도 처리합니다.
    
    Args:
        json_path: JSON 경로 (예: "IMM_0800.Page1.KeepPageSeparate[0].FamilyMember.OptionsQ2[0]")
        field_xpath_map: JSON 경로 -> XFA 경로 매핑
        base_tag: 베이스 태그
    
    Returns:
        XFA 상대 경로 또는 None
    """
    if not field_xpath_map:
        return None
    
    import re
    
    # 1. 정확한 경로 매칭 시도
    if json_path in field_xpath_map:
        return field_xpath_map[json_path]
    
    # 2. 배열 인덱스가 포함된 경로의 경우, 구조적으로 동일한 경로 찾기
    # 예: "IMM_0800.Page1.KeepPageSeparate[0].FamilyMember.OptionsQ2[0]"
    # -> 구조적으로 동일한 경로를 찾기 위해 인덱스를 제거한 경로로 비교
    clean_path = re.sub(r'\[\d+\]', '', json_path)
    
    # 인덱스가 제거된 경로와 구조적으로 동일한 모든 키 찾기
    matching_keys = []
    for key in field_xpath_map.keys():
        key_clean = re.sub(r'\[\d+\]', '', key)
        if key_clean == clean_path:
            matching_keys.append(key)
    
    if matching_keys:
        # 정확한 인덱스 매칭 시도
        # json_path의 인덱스 패턴 추출
        json_indices = [int(m.group(1)) for m in re.finditer(r'\[(\d+)\]', json_path)]
        
        # 각 매칭 키의 인덱스 패턴과 비교
        best_match = None
        best_score = -1
        
        for key in matching_keys:
            key_indices = [int(m.group(1)) for m in re.finditer(r'\[(\d+)\]', key)]
            
            # 인덱스 패턴이 일치하는지 확인
            # 예: json_path가 [0, 0]이고 key가 [0, 0]이면 완벽 매칭
            if len(json_indices) == len(key_indices):
                # 모든 인덱스가 일치하는지 확인
                if all(json_indices[i] == key_indices[i] for i in range(len(json_indices))):
                    return field_xpath_map[key]
                
        # 완벽 매칭이 없으면 첫 번째 매칭 키 사용 (인덱스가 다를 수 있으므로)
        # 하지만 이 경우 경고를 출력하여 디버깅에 도움
        if matching_keys:
            logger.debug(f"인덱스 완벽 매칭 실패: json_path={json_path}, json_indices={json_indices}, 첫 번째 매칭 키 사용: {matching_keys[0]}")
        return field_xpath_map[matching_keys[0]]
    
    # 3. 경로의 접두사로 매칭 시도
    path_parts = json_path.split(".")
    for i in range(len(path_parts), 0, -1):
        prefix = ".".join(path_parts[:i])
        if prefix in field_xpath_map:
            return field_xpath_map[prefix]
    
    # 4. 필드 이름으로 매칭 시도 (JSON 구조와 PDF 구조가 다를 수 있음)
    # 예: IMM_0800.Page1.PersonalDetails.Language.language -> IMM_0800.Page1.Language.language
    # 마지막 두 부분(필드 이름)을 사용하여 매칭
    if len(path_parts) >= 2:
        field_name = path_parts[-1]  # language
        parent_name = path_parts[-2]  # Language
        
        # base_tag.Page1.{parent_name}.{field_name} 형태로 검색
        search_pattern = f"{base_tag}.Page1.{parent_name}.{field_name}"
        if search_pattern in field_xpath_map:
            return field_xpath_map[search_pattern]
        
        # base_tag.{parent_name}.{field_name} 형태로도 검색
        search_pattern2 = f"{base_tag}.{parent_name}.{field_name}"
        if search_pattern2 in field_xpath_map:
            return field_xpath_map[search_pattern2]
        
        # 필드 이름만으로 검색 (마지막 부분)
        for key in field_xpath_map.keys():
            if key.endswith(f".{field_name}") and parent_name in key:
                return field_xpath_map[key]
    
    return None

def _traverse_json_to_xfa(
    form: LET._Element,
    data: dict,
    base_tag: str,
    current_path: str = "",
    field_xpath_map: Dict[str, str] = None,
    field_type_map: Dict[str, Dict] = None
):
    """
    current_path / json_path 모두 base_tag를 포함한 full path를 사용:
    예: "IMM_0800.Page1.PersonalDetails.FamilyName"
    """
    for key, value in data.items():
        # current_path가 비어 있으면 base_tag부터 시작
        if current_path:
            json_path = f"{current_path}.{key}"
        else:
            json_path = f"{base_tag}.{key}"  # 항상 base_tag 포함

        if isinstance(value, dict):
            _traverse_json_to_xfa(form, value, base_tag, json_path, field_xpath_map, field_type_map)
        elif isinstance(value, list):
            # 필드 타입 확인
            field_type_info = field_type_map.get(json_path) if field_type_map else None
            # 배열 인덱스가 포함된 경로인 경우, 인덱스를 제거해서 타입 정보 찾기 시도
            if not field_type_info:
                clean_json_path = re.sub(r'\[\d+\]', '', json_path)
                field_type_info = field_type_map.get(clean_json_path) if field_type_map else None
            
            field_type = field_type_info.get("type") if field_type_info else None
            
            # radio 타입 필드도 일반 배열과 동일하게 처리
            # (배열의 각 값을 순서대로 각 필드에 매핑)
            # 일반 배열 처리
            for i, item in enumerate(value):
                array_path = f"{json_path}[{i}]"
                logger.debug(f"배열 처리: json_path={json_path}, i={i}, array_path={array_path}")
                if isinstance(item, dict):
                    _traverse_json_to_xfa(form, item, base_tag, array_path, field_xpath_map, field_type_map)
                else:
                    # field_xpath_map에서 경로 찾기 (개선된 매칭 로직 사용)
                    xfa_path = _find_matching_xpath(array_path, field_xpath_map, base_tag)
                    
                    if not xfa_path:
                        # 매칭 실패 시 기본 경로 변환 시도
                        clean_json_path = re.sub(r'\[\d+\]', '', json_path)
                        xfa_path = _json_path_to_xfa_path(clean_json_path, base_tag, field_xpath_map)
                        logger.warning(f"field_xpath_map에서 매칭 실패, 기본 경로 변환: {array_path} -> {xfa_path}")
                    
                    if xfa_path:
                        # array_path의 타입 정보 찾기 (없으면 clean 경로로 시도)
                        array_field_type_info = field_type_map.get(array_path) if field_type_map else None
                        if not array_field_type_info:
                            clean_array_path = re.sub(r'\[\d+\]', '', array_path)
                            array_field_type_info = field_type_map.get(clean_array_path) if field_type_map else field_type_info
                        converted_value = _convert_value_for_field("" if item is None else str(item), array_field_type_info)
                        logger.debug(f"값 설정: {xfa_path} = {converted_value}")
                        set_node(form, xfa_path, converted_value)
                    else:
                        logger.warning(f"XFA 경로를 찾을 수 없음: array_path={array_path}")
        else:
            # field_xpath_map에서 경로 찾기 (개선된 매칭 로직 사용)
            xfa_path = _find_matching_xpath(json_path, field_xpath_map, base_tag)
            
            if not xfa_path:
                # 매핑에 없으면 기본 경로 생성
                xfa_path = _json_path_to_xfa_path(json_path, base_tag, field_xpath_map)
                logger.warning(f"field_xpath_map에서 매칭 실패, 기본 경로 생성: json_path={json_path}, xfa_path={xfa_path}, field_xpath_map keys (일부)={list(field_xpath_map.keys())[:10] if field_xpath_map else []}")
            else:
                logger.debug(f"field_xpath_map에서 경로 찾음: json_path={json_path}, xfa_path={xfa_path}")
            
            # 필드 타입 정보 찾기 (여러 경로로 시도)
            field_type_info = None
            radio_parent_path = None  # 부모 경로에서 라디오 타입을 찾은 경우 저장
            if field_type_map:
                # 1. 정확한 경로로 먼저 시도
                field_type_info = field_type_map.get(json_path)
                if field_type_info:
                    logger.debug(f"필드 타입 정보 찾음 (정확한 경로): {json_path} -> {field_type_info}")
                
                # 2. 배열 인덱스 제거한 경로로 시도
                if not field_type_info:
                    clean_json_path = re.sub(r'\[\d+\]', '', json_path)
                    field_type_info = field_type_map.get(clean_json_path)
                    if field_type_info:
                        logger.debug(f"필드 타입 정보 찾음 (인덱스 제거): {clean_json_path} -> {field_type_info}")
                
                # 3. 부모 경로로 시도 (라디오 그룹의 경우 필드 이름이 그룹 이름과 다를 수 있음)
                # 예: "IMM_0800.Page1.PersonalDetails.Gender.RadioButtonList" -> "IMM_0800.Page1.PersonalDetails.Gender"
                # 예: "IMM_0800.Page1.Language.language" -> "IMM_0800.Page1.Language"
                if not field_type_info:
                    path_parts = json_path.split(".")
                    for i in range(len(path_parts) - 1, 0, -1):
                        parent_path = ".".join(path_parts[:i])
                        parent_type_info = field_type_map.get(parent_path)
                        if parent_type_info and parent_type_info.get("type") == "radio":
                            field_type_info = parent_type_info
                            radio_parent_path = parent_path
                            logger.debug(f"부모 경로에서 라디오 타입 찾음: {parent_path} -> {json_path}, options={parent_type_info.get('options', [])}")
                            break
                        # 부모 경로의 자식 필드가 라디오인 경우도 확인
                        # 예: "IMM_0800.Page1.Language.language" -> "IMM_0800.Page1.Language.language"가 라디오 타입
                        child_path = ".".join(path_parts[:i+1])
                        child_type_info = field_type_map.get(child_path)
                        if child_type_info and child_type_info.get("type") == "radio":
                            field_type_info = child_type_info
                            radio_parent_path = parent_path  # 부모 경로를 라디오 그룹 경로로 사용
                            logger.debug(f"자식 경로에서 라디오 타입 찾음: {child_path} -> {json_path}, parent={parent_path}, options={child_type_info.get('options', [])}")
                            break
                
                # 4. 필드 이름으로 직접 검색 (라디오 버튼의 경우)
                if not field_type_info:
                    field_name = json_path.split(".")[-1]
                    # field_type_map에서 필드 이름이 포함된 경로 찾기
                    for path, type_info in field_type_map.items():
                        if type_info.get("type") == "radio" and (path.endswith(f".{field_name}") or path.endswith(f"/{field_name}")):
                            field_type_info = type_info
                            logger.debug(f"필드 이름으로 라디오 타입 찾음: {path} -> {json_path}")
                            break
                
                # 5. 필드 타입 정보를 찾지 못한 경우 로깅
                if not field_type_info:
                    logger.debug(f"필드 타입 정보를 찾을 수 없음: json_path={json_path}, field_type_map keys (일부)={list(field_type_map.keys())[:20] if field_type_map else []}")
            
            # 라디오 버튼 그룹(exclGroup) 처리
            if field_type_info and field_type_info.get("type") == "radio":
                options = field_type_info.get("options", [])
                logger.info(f"라디오 버튼 처리 시작: json_path={json_path}, value={value}, options={options}, xfa_path={xfa_path}, radio_parent_path={radio_parent_path}")
                
                # datasets.xml에서는 라디오 버튼이 개별 필드로 저장될 수 있음
                # 예: <Language><language>N</language></Language>
                # 이 경우 개별 필드에 값을 설정해야 함
                
                # field_xpath_map에 현재 경로가 있으면 datasets.xml의 개별 필드로 처리
                is_individual_field = field_xpath_map and json_path in field_xpath_map
                logger.info(f"라디오 버튼 필드 타입 판단: json_path={json_path}, is_individual_field={is_individual_field}, json_path in field_xpath_map={json_path in field_xpath_map if field_xpath_map else False}, xfa_path={xfa_path}")
                
                if is_individual_field and xfa_path:
                    # datasets.xml에서 라디오 버튼은 RadioButtonList 자식 요소로 저장되어야 함
                    # 예: <Language><RadioButtonList>1</RadioButtonList></Language>
                    # xfa_path가 ./Page1/Language/language인 경우, ./Page1/Language/RadioButtonList로 변경
                    
                    # 부모 경로 찾기 (마지막 부분 제거)
                    if "/" in xfa_path:
                        path_parts = xfa_path.split("/")
                        # 마지막 부분 제거하고 RadioButtonList 추가
                        parent_path = "/".join(path_parts[:-1])
                        radio_button_list_path = f"{parent_path}/RadioButtonList"
                    else:
                        radio_button_list_path = f"{xfa_path}/RadioButtonList"
                    
                    # 값 변환: "Y" -> "Yes", "N" -> "No" 등
                    converted_value = _convert_value_for_field("" if value is None else str(value), field_type_info)
                    
                    # 옵션 이름을 숫자 인덱스로 변환 (datasets.xml에서는 인덱스로 저장됨)
                    final_value = converted_value
                    if options:
                        # 먼저 숫자 인덱스인지 확인
                        try:
                            idx = int(converted_value) if converted_value else -1
                            if 1 <= idx <= len(options):  # 1-based 인덱스
                                # 이미 숫자 인덱스이면 그대로 사용
                                final_value = str(idx)
                                logger.debug(f"라디오 버튼 RadioButtonList (숫자 인덱스): json_path={json_path}, value={converted_value} -> {final_value}")
                            elif 0 <= idx < len(options):  # 0-based 인덱스
                                final_value = str(idx + 1)  # 1-based로 변환
                                logger.debug(f"라디오 버튼 RadioButtonList (0-based -> 1-based): json_path={json_path}, value={converted_value} -> {final_value}")
                        except (ValueError, TypeError):
                            # 숫자가 아니면 옵션 이름으로 처리
                            if converted_value in options:
                                # 옵션 이름이면 인덱스로 변환 (1-based)
                                try:
                                    idx = options.index(converted_value) + 1
                                    final_value = str(idx)
                                    logger.debug(f"라디오 버튼 RadioButtonList (옵션 이름 -> 인덱스): json_path={json_path}, option={converted_value} -> {final_value}")
                                except ValueError:
                                    pass
                            else:
                                # 옵션 이름이 아니면 변환된 값 사용 (이미 숫자일 수 있음)
                                logger.debug(f"라디오 버튼 RadioButtonList (변환된 값): json_path={json_path}, value={converted_value}")
                    
                    # RadioButtonList 노드 찾기 또는 생성
                    # set_node를 사용하여 직접 설정 (노드가 없으면 생성하도록 set_node 수정 필요)
                    # 하지만 set_node는 노드를 생성하지 않으므로, 직접 생성해야 함
                    # 부모 노드 찾기: xfa_path가 ./Page1/Language/language인 경우
                    # parent_path는 ./Page1/Language
                    parent_path = "/".join(xfa_path.split("/")[:-1])
                    if not parent_path.startswith("./"):
                        parent_path = f"./{parent_path}"
                    
                    # XPath로 부모 노드 찾기
                    parent_path_parts = [p for p in parent_path.replace("./", "").split("/") if p]
                    parent_node = form
                    for part in parent_path_parts:
                        # 인덱스 처리: Page1[1] -> Page1의 첫 번째
                        if "[" in part and "]" in part:
                            tag_name = part.split("[")[0]
                            idx_str = part.split("[")[1].split("]")[0]
                            try:
                                idx = int(idx_str) - 1  # 1-based -> 0-based
                                children = [c for c in parent_node if strip_ns(c.tag) == tag_name]
                                if idx < len(children):
                                    parent_node = children[idx]
                                else:
                                    parent_node = None
                                    break
                            except (ValueError, IndexError):
                                parent_node = None
                                break
                        else:
                            # 태그 이름으로 찾기
                            children = []
                            for c in parent_node:
                                c_tag = c.tag
                                if not isinstance(c_tag, str):
                                    if hasattr(c_tag, '__call__'):
                                        continue
                                    c_tag = str(c_tag)
                                if strip_ns(c_tag) == part:
                                    children.append(c)
                            
                            # 태그 이름으로 못 찾으면 name 속성으로 찾기
                            if not children:
                                children = [c for c in parent_node if c.get("name") == part]
                            
                            if children:
                                parent_node = children[0]
                            else:
                                parent_node = None
                                logger.debug(f"부모 노드 찾기 실패: part={part}, parent_node={strip_ns(parent_node.tag) if parent_node is not None else None}")
                                break
                    
                    if parent_node is not None:
                        # RadioButtonList 노드 찾기 또는 생성
                        radio_list_node = None
                        for child in parent_node:
                            if strip_ns(child.tag) == "RadioButtonList":
                                radio_list_node = child
                                break
                        
                        if radio_list_node is None:
                            # RadioButtonList 노드 생성
                            from lxml.etree import Element
                            NS_XFA_DATA = "http://www.xfa.org/schema/xfa-data/1.0/"
                            radio_list_node = Element(f"{{{NS_XFA_DATA}}}RadioButtonList")
                            parent_node.append(radio_list_node)
                            logger.info(f"RadioButtonList 노드 생성: {parent_path}/RadioButtonList")
                        
                        # 값 설정
                        radio_list_node.text = final_value
                        logger.info(f"라디오 버튼 RadioButtonList 설정: json_path={json_path}, parent_path={parent_path}, value={final_value}")
                    else:
                        logger.warning(f"부모 노드를 찾을 수 없음: parent_path={parent_path}, xfa_path={xfa_path}, form_tag={strip_ns(form.tag) if form is not None else None}")
                    
                    # datasets.xml에 인덱스로 설정했지만, form.xml과 template.xml에서도 라디오 그룹으로 처리해야 함
                    # _fill_form_radio_groups와 _fill_template_radio_groups에서 처리하므로 여기서는 인덱스만 설정
                elif options:
                    # 라디오 그룹으로 처리 (form.xml의 경우)
                    # 부모 경로에서 라디오 타입을 찾은 경우, xfa_path도 부모 경로로 조정
                    if radio_parent_path:
                        # 부모 경로의 xfa_path 찾기
                        parent_xfa_path = _find_matching_xpath(radio_parent_path, field_xpath_map, base_tag)
                        if parent_xfa_path:
                            xfa_path = parent_xfa_path
                            logger.debug(f"라디오 그룹 경로로 조정 (field_xpath_map): {json_path} -> {xfa_path}")
                        else:
                            # 부모 경로의 xfa_path를 찾지 못하면 기본 경로 생성
                            parent_xfa_path = _json_path_to_xfa_path(radio_parent_path, base_tag, field_xpath_map)
                            if parent_xfa_path:
                                xfa_path = parent_xfa_path
                                logger.debug(f"라디오 그룹 경로 생성: {json_path} -> {xfa_path}")
                    elif not xfa_path:
                        # xfa_path가 없고 radio_parent_path도 없으면 현재 경로에서 부모 경로 생성
                        path_parts = json_path.split(".")
                        if len(path_parts) > 1:
                            parent_path = ".".join(path_parts[:-1])
                            xfa_path = _json_path_to_xfa_path(parent_path, base_tag, field_xpath_map)
                            logger.debug(f"라디오 그룹 경로 생성 (현재 경로의 부모): {json_path} -> {xfa_path}")
                    
                    if not xfa_path:
                        logger.warning(f"라디오 버튼 그룹 xfa_path를 찾을 수 없음: json_path={json_path}, radio_parent_path={radio_parent_path}")
                        # 마지막 시도: 현재 경로에서 부모 경로 생성
                        path_parts = json_path.split(".")
                        if len(path_parts) > 1:
                            parent_path = ".".join(path_parts[:-1])
                            xfa_path = _json_path_to_xfa_path(parent_path, base_tag, field_xpath_map)
                            logger.debug(f"라디오 그룹 경로 생성 (최종 시도): {json_path} -> {xfa_path}")
                    
                    if xfa_path:
                        # 값 변환: "Y" -> "Yes", "N" -> "No" 등
                        converted_value = _convert_value_for_field("" if value is None else str(value), field_type_info)
                        
                    # 값이 숫자 문자열이면 해당 인덱스의 옵션 선택
                    # 값이 옵션 이름이면 해당 옵션 선택
                        selected_option = None
                        try:
                            idx = int(converted_value) if converted_value else -1
                            if 1 <= idx <= len(options):  # 1-based 인덱스
                                selected_option = options[idx - 1]
                            elif 0 <= idx < len(options):  # 0-based 인덱스
                                selected_option = options[idx]
                        except (ValueError, TypeError):
                            # 값이 숫자가 아니면 옵션 이름으로 매칭 시도
                            if converted_value in options:
                                selected_option = converted_value
                            else:
                                # "Y", "N" 같은 값도 "Yes", "No"로 변환 시도
                                value_map = {"Y": "Yes", "N": "No", "1": "Yes", "0": "No"}
                                if converted_value in value_map and value_map[converted_value] in options:
                                    selected_option = value_map[converted_value]
                                # 대소문자 무시 매칭 시도
                                elif options:
                                    for opt in options:
                                        if opt.lower() == converted_value.lower():
                                            selected_option = opt
                                            break
                        
                        if selected_option:
                            # 라디오 버튼 그룹 내부의 선택된 옵션 필드에 값 설정
                            # 예: ./Page1/ApplyFrom/ApplyFromOpt -> ./Page1/ApplyFrom/ApplyFromOpt/OutsideCanada
                            # 옵션 이름을 필드 이름으로 사용 시도
                            option_xpath = f"{xfa_path}/{selected_option}"
                            logger.info(f"라디오 버튼 그룹 선택 시도: json_path={json_path}, value={value}, converted={converted_value}, option={selected_option}, option_xpath={option_xpath}")
                            set_node(form, option_xpath, "1")
                            
                            # 선택되지 않은 다른 옵션들은 nil="true"로 설정 (datasets.xml에서도)
                            # 하지만 datasets.xml은 개별 필드로 저장되므로 여기서는 form.xml만 처리
                            # form.xml 처리는 _fill_form_radio_groups에서 수행
                            
                            # 대소문자 변형도 시도 (옵션 이름이 정확히 일치하지 않을 수 있음)
                            for opt in options:
                                if opt != selected_option and opt.lower() == selected_option.lower():
                                    option_xpath_variant = f"{xfa_path}/{opt}"
                                    logger.debug(f"대소문자 변형으로 추가 시도: {option_xpath_variant}")
                                    set_node(form, option_xpath_variant, "1")
                            
                            # 옵션 이름의 첫 글자를 소문자로 변환 시도
                            option_lower = selected_option[0].lower() + selected_option[1:] if selected_option else ""
                            if option_lower and option_lower != selected_option:
                                option_xpath_lower = f"{xfa_path}/{option_lower}"
                                logger.debug(f"소문자 변형으로 추가 시도: {option_xpath_lower}")
                                set_node(form, option_xpath_lower, "1")
                            
                            # 옵션 이름을 공백 제거하고 소문자로 변환한 버전도 시도
                            option_no_space = selected_option.replace(" ", "")
                            if option_no_space != selected_option:
                                option_xpath_no_space = f"{xfa_path}/{option_no_space}"
                                logger.debug(f"공백 제거 변형으로 추가 시도: {option_xpath_no_space}")
                                set_node(form, option_xpath_no_space, "1")
                            
                            # 옵션 이름을 모두 소문자로 변환한 버전도 시도
                            option_all_lower = selected_option.lower()
                            if option_all_lower != selected_option:
                                option_xpath_all_lower = f"{xfa_path}/{option_all_lower}"
                                logger.debug(f"모두 소문자 변형으로 추가 시도: {option_xpath_all_lower}")
                                set_node(form, option_xpath_all_lower, "1")
                            
                            # datasets.xml의 개별 필드에도 값 설정 (양쪽 모두 설정하여 호환성 확보)
                            if xfa_path and is_individual_field:
                                logger.debug(f"라디오 버튼 개별 필드에도 값 설정: json_path={json_path}, xfa_path={xfa_path}, value={converted_value}")
                                # 옵션 이름을 인덱스로 변환하여 설정
                                try:
                                    idx = options.index(selected_option) + 1
                                    set_node(form, xfa_path, str(idx))
                                except (ValueError, IndexError):
                                    set_node(form, xfa_path, converted_value)
                        else:
                            logger.warning(f"라디오 버튼 옵션을 찾을 수 없음: json_path={json_path}, value={value}, converted={converted_value}, options={options}, xfa_path={xfa_path}")
                            # 옵션을 찾지 못했지만, datasets.xml의 개별 필드로 처리 시도
                            if xfa_path:
                                logger.info(f"라디오 버튼 개별 필드로 폴백 처리: json_path={json_path}, xfa_path={xfa_path}, value={converted_value}")
                                set_node(form, xfa_path, converted_value)
                    else:
                        logger.warning(f"라디오 버튼 그룹 xfa_path가 없음: json_path={json_path}")
                else:
                    # 옵션이 없으면 일반 필드처럼 처리
                    if xfa_path:
                        converted_value = _convert_value_for_field("" if value is None else str(value), field_type_info)
                        logger.debug(f"값 설정 시도 (라디오, 옵션 없음): json_path={json_path}, xfa_path={xfa_path}, value={value}")
                        set_node(form, xfa_path, converted_value)
            else:
                # 일반 필드 처리
                converted_value = _convert_value_for_field("" if value is None else str(value), field_type_info)
                logger.info(f"일반 필드 값 설정: json_path={json_path}, xfa_path={xfa_path}, value={value}, converted_value={converted_value}, field_type={field_type_info.get('type') if field_type_info else 'unknown'}")
                set_node(form, xfa_path, converted_value)

def _set_form_from_json(
    root: LET._Element,
    data: dict,
    base_tag_hint: str | None = None,
    field_xpath_map: Dict[str, str] = None,
    field_type_map: Dict[str, Dict] = None
):
    """JSON 데이터를 XFA 폼에 채웁니다. FIELD_MAP 없이 JSON 구조를 직접 사용합니다."""
    # root는 datasets.xml의 루트이므로, base_node (IMM_0800)를 찾아야 함
    # root에서 직접 base_node 찾기 (serialize/parse 없이)
    form = None
    auto_base = None
    
    # root의 구조: <datasets><data><IMM_0800>...</IMM_0800></data></datasets>
    # root의 직접 자식 중에서 "data" 찾기
    data_node = None
    for child in root:
        child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if child_tag == "data":
            data_node = child
            break
    
    # data 노드의 직접 자식 중에서 base_node 찾기
    if data_node is not None:
        for child in data_node:
            child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if child_tag and (child_tag.startswith("IMM_") or child_tag.startswith("Form") or child_tag.isalnum()):
                form = child
                auto_base = child_tag
                break
    
    # 여전히 못 찾으면 root 사용
    if form is None:
        form = root
        from lxml.etree import QName
        auto_base = QName(root).localname
    
    base_tag = base_tag_hint or auto_base

    # data가 {base_tag: {...}} 형태면 내부 객체 사용
    # 중첩 구조 처리: {"fields": {"IMM_0800": {...}}} 형태면 IMM_0800 내부 사용
    if base_tag in data and isinstance(data[base_tag], dict):
        target_data = data[base_tag]
    elif len(data) == 1:
        # 최상위 키가 하나이고, 그 안에 base_tag가 있으면 중첩 구조
        top_key = next(iter(data.keys()))
        if isinstance(data[top_key], dict) and base_tag in data[top_key]:
            target_data = data[top_key][base_tag]
        else:
            target_data = data
    else:
        target_data = data

    # 디버깅: OptionsQ2 관련 키들 출력
    if field_xpath_map:
        optionsq2_keys = [k for k in field_xpath_map.keys() if "OptionsQ2" in k]
        if optionsq2_keys:
            logger.info(f"field_xpath_map에서 OptionsQ2 관련 키들: {optionsq2_keys}")

    # current_path를 base_tag로 시작해서 full JSON path를 일관되게 사용
    _traverse_json_to_xfa(form, target_data, base_tag, base_tag, field_xpath_map, field_type_map)

def get_base_tag_from_json(data: dict) -> str | None:
    """JSON 데이터에서 base_tag를 추론합니다."""
    # JSON의 최상위 키를 base_tag로 사용
    if len(data) == 1:
        top_key = next(iter(data.keys()))
        # 중첩 구조 처리: {"fields": {"IMM_0800": {...}}} 형태면 IMM_0800 반환
        if isinstance(data[top_key], dict) and len(data[top_key]) == 1:
            nested_key = next(iter(data[top_key].keys()))
            # 일반적인 폼 이름 패턴 (IMM_0800, Form1 등)이면 중첩된 키 사용
            if nested_key and (nested_key.startswith("IMM_") or nested_key.startswith("Form") or nested_key.isalnum()):
                return nested_key
        return top_key
    # 여러 키가 있으면 첫 번째 키를 반환
    return next(iter(data.keys()), None)

def _build_field_xpath_map(pdf_path: Path, base_tag: str) -> Tuple[Dict[str, str], Dict[str, Dict]]:
    """
    PDF에서 필드 구조를 추출하여
    - JSON 경로 -> XFA 상대 경로
    - JSON 경로 -> 필드 타입 정보
    를 생성합니다.

    JSON 경로 예: "IMM_0800.Page1.PersonalDetails.FamilyName"
    
    중요: extract_field_values와 동일한 키를 생성하기 위해
    _build_field_template과 동일한 방식으로 필드 키를 생성합니다.
    """
    from app.services.pdf_extract_service import (
        _find_base_form_node, _collect_leaf_fields,
        _collect_form_field_paths_from_pdf, _build_field_template
    )
    from app.utils.utils import read_datasets_from_pdf, parse_xml, strip_ns

    # _build_field_template을 사용하여 필드 템플릿 생성 (키 일치 보장)
    # 이렇게 하면 extract_field_values와 동일한 키 구조를 가집니다
    field_template = _build_field_template(pdf_path)

    # datasets.xml 추출
    xml_bytes = read_datasets_from_pdf(pdf_path)
    base_node, _ = _find_base_form_node(xml_bytes)
    fields = _collect_leaf_fields(base_node)

    # 타입 정보: nested + JSON path 타입 map
    _, json_path_type_map = extract_field_types_with_path_map(pdf_path)

    field_xpath_map: Dict[str, str] = {}
    field_type_map: Dict[str, Dict] = {}

    # 1. datasets.xml의 필드들 추가
    for field in fields:
        # JSON full path 생성 (base_tag 포함)
        json_parts = []
        for tag, idx in field.json_path:
            if idx >= 0:
                json_parts.append(f"{tag}[{idx}]")
            else:
                json_parts.append(tag)
        json_path = f"{base_tag}.{'.'.join(json_parts)}"

        # 템플릿에 있는 키만 추가 (extract_field_values와 동일한 키 집합 유지)
        # 템플릿에 없는 키는 스킵
        if not _key_exists_in_template(field_template, base_tag, field.json_path):
            logger.debug(f"템플릿에 없는 필드 스킵: json_path={json_path}")
            continue

        # XFA 상대 경로는 field.rel_xpath 그대로 사용
        field_xpath_map[json_path] = field.rel_xpath
        logger.debug(f"필드 매핑 (datasets): json_path={json_path}, rel_xpath={field.rel_xpath}")

        # 타입 정보: json_path_type_map에서 그대로 가져오기 (없으면 text)
        type_info = json_path_type_map.get(json_path)
        if not type_info:
            # 배열 인덱스 제거해서 한번 더 시도
            clean_json_path = re.sub(r'\[\d+\]', '', json_path)
            type_info = json_path_type_map.get(clean_json_path, {"type": "text"})
        field_type_map[json_path] = type_info

    # 2. form.xml의 필드들도 추가 (datasets에 없는 필드들)
    # 템플릿에서 form.xml 필드 경로를 추출하여 매핑 (extract_field_values와 동일한 키 집합 유지)
    form_base_tag, form_field_paths = _collect_form_field_paths_from_pdf(pdf_path)
    if form_base_tag and form_field_paths:
        if form_base_tag != base_tag:
            logger.warning(f"datasets base_tag={base_tag}, form base_tag={form_base_tag} 불일치")
        
        # 템플릿에서 form.xml 필드 경로 추출
        def extract_template_paths(obj, prefix=''):
            paths = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    current_path = f'{prefix}.{k}' if prefix else k
                    if isinstance(v, (dict, list)):
                        paths.extend(extract_template_paths(v, current_path))
                    else:
                        paths.append(current_path)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    current_path = f'{prefix}[{i}]'
                    if isinstance(item, (dict, list)):
                        paths.extend(extract_template_paths(item, current_path))
                    else:
                        paths.append(current_path)
            return paths
        
        template_paths = extract_template_paths(field_template.get(base_tag, {}))
        
        # 템플릿에 있는 경로 중 datasets에 없는 것만 추가
        form_field_count = 0
        for template_path in template_paths:
            full_json_path = f"{base_tag}.{template_path}" if template_path else base_tag
            # 이미 datasets에 있는 필드는 스킵
            if full_json_path in field_xpath_map:
                continue
            
            # form.xml의 필드는 _json_path_to_xfa_path를 사용하여 XFA 경로 생성
            xfa_path = _json_path_to_xfa_path(full_json_path, base_tag, None)
            field_xpath_map[full_json_path] = xfa_path
            logger.debug(f"필드 매핑 (form): json_path={full_json_path}, xfa_path={xfa_path}")
            form_field_count += 1
            
            # 타입 정보: json_path_type_map에서 가져오기 (없으면 text)
            type_info = json_path_type_map.get(full_json_path)
            if not type_info:
                # 배열 인덱스 제거해서 한번 더 시도
                clean_json_path = re.sub(r'\[\d+\]', '', full_json_path)
                type_info = json_path_type_map.get(clean_json_path, {"type": "text"})
            field_type_map[full_json_path] = type_info

    logger.info(f"필드 매핑 완료: 총 {len(field_xpath_map)}개 필드 (datasets: {len(fields)}개, form: {form_field_count}개)")
    return field_xpath_map, field_type_map

def fill_pdf(
    template_pdf: str | Path,
    data: dict,
    out_pdf: str | Path,
    base_tag_hint: str | None = None,
) -> None:
    template_pdf = Path(template_pdf)
    out_pdf = Path(out_pdf)

    # 1) datasets.xml 채우기 (기존 로직 유지)
    datasets_xml = read_datasets_from_pdf(template_pdf)
    root = parse_xml(datasets_xml)

    # base_tag 추론 (예: IMM_0800)
    base_tag = base_tag_hint or get_base_tag_from_json(data)
    if not base_tag:
        raise ValueError("base_tag를 추론할 수 없습니다.")

    # field XPath 매핑 + 타입 정보 (checkbox/radio 등 처리용)
    field_xpath_map, field_type_map = _build_field_xpath_map(template_pdf, base_tag)

    # JSON → datasets (xfa:data) 적용
    _set_form_from_json(
        root,
        data,
        base_tag_hint=base_tag,
        field_xpath_map=field_xpath_map,
        field_type_map=field_type_map,
    )

    new_xml = serialize_xml(root)

    # 1) 먼저 datasets 를 채운 PDF 를 out_pdf 로 생성
    write_datasets_to_pdf(template_pdf, new_xml, out_pdf)

    # 2) 그 다음, out_pdf 의 template XFA 안에 unbound 필드들 채우기
    _fill_unbound_template_fields(Path(out_pdf), data)
    
    # 3) template.xml의 라디오 버튼 그룹에도 값 설정 (unbound 필드 채우기 이후에 실행하여 덮어쓰기 방지)
    _fill_template_radio_groups(Path(out_pdf), data, base_tag, field_xpath_map, field_type_map)
    
    # 4) form.xml의 라디오 버튼 그룹에도 값 설정
    _fill_form_radio_groups(Path(out_pdf), data, base_tag, field_xpath_map, field_type_map)

def _get_base_dir() -> Path:
    """프로젝트 루트 디렉토리 반환"""
    return Path(__file__).parent.parent.parent

def _create_temp_output_file(form_name: str) -> Path:
    """임시 출력 파일 생성"""
    temp_file = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".pdf",
        prefix=f"{form_name}_filled_",
        dir=None
    )
    temp_file.close()
    return Path(temp_file.name)

def _cleanup_temp_file(file_path: Path) -> None:
    """임시 파일 삭제"""
    try:
        if file_path.exists():
            file_path.unlink()
            logger.info(f"임시 파일 삭제 완료: {file_path}")
    except Exception as e:
        logger.error(f"임시 파일 삭제 실패: {file_path} - {e}")

async def fill_pdf_with_data(
    filename: str,
    fields_data: Dict[str, Any],
    background_tasks: BackgroundTasks
) -> FileResponse:
    """PDF 채우기 및 다운로드 파일 생성
    
    Args:
        filename: PDF 파일명
        fields_data: 채울 필드 데이터
        background_tasks: 백그라운드 작업 관리자
        
    Returns:
        FileResponse 객체
        
    Raises:
        HTTPException: 처리 실패 시
    """
    base_dir = _get_base_dir()
    upload_dir = base_dir / "uploads"
    file_path = upload_dir / filename
    
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"파일 '{filename}'을 찾을 수 없습니다. 먼저 /upload-and-extract로 파일을 업로드해주세요."
        )
    
    logger.info(f"PDF 파일 찾음: {file_path}, fields keys: {list(fields_data.keys()) if fields_data else None}")
    
    try:
        # base_tag 추론
        base_tag = get_base_tag_from_json(fields_data)
        logger.info(f"Base tag: {base_tag}")
        
        # 임시 파일 생성
        form_name = file_path.stem
        output_file = _create_temp_output_file(form_name)
        
        try:
            # PDF 채우기
            logger.info(f"PDF 채우기 시작: {file_path} -> {output_file}")
            fill_pdf(file_path, fields_data, output_file, base_tag_hint=base_tag)
            logger.info(f"PDF 채우기 완료: {output_file}")
            
            # 다운로드 후 파일 삭제를 백그라운드 작업으로 등록
            background_tasks.add_task(_cleanup_temp_file, output_file)
            
            return FileResponse(
                path=str(output_file),
                filename=f"{form_name}_filled.pdf",
                media_type="application/pdf"
            )
        except Exception as e:
            # 오류 발생 시 임시 파일 삭제
            if output_file.exists():
                output_file.unlink()
            raise
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF 채우기 중 오류: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"PDF 채우기 중 오류가 발생했습니다: {str(e)}"
        )

def _get_value_by_full_json_path(data: dict, full_path: str) -> str | None:
    """
    full_path 예: "IMM_0800.Page1.ContactInformation.Information.TelephoneNo"
    """
    parts = full_path.split(".")
    cur: Any = data
    for p in parts:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    # 단순 값만 허용
    if cur is None:
        return None
    if isinstance(cur, (str, int, float)):
        return str(cur)
    return None


def _write_form_to_pdf(pdf_path: Path, form_xml: bytes) -> None:
    """
    PDF의 form.xml 스트림을 업데이트합니다.
    """
    import pikepdf
    
    with pikepdf.open(str(pdf_path), allow_overwriting_input=True) as pdf:
        acro = pdf.Root.get("/AcroForm", None)
        if not acro:
            return
        xfa = acro.get("/XFA", None)
        if not xfa:
            return

        if isinstance(xfa, pikepdf.Array):
            parts = list(xfa)
            for i in range(0, len(parts), 2):
                nm = str(parts[i])
                st = parts[i + 1]
                if "form" in nm.lower() and "template" not in nm.lower():
                    # form.xml 스트림 내용을 새 XML로 교체
                    st_obj = st
                    st_obj.write(form_xml)
                    break
        elif isinstance(xfa, pikepdf.Stream):
            # 단일 XFA 스트림인 경우 전체를 교체
            xfa.write(form_xml)

        pdf.save(str(pdf_path))

def _fill_template_radio_groups(
    pdf_path: Path,
    data: dict,
    base_tag: str,
    field_xpath_map: Dict[str, str],
    field_type_map: Dict[str, Dict]
) -> None:
    """
    template.xml의 라디오 버튼 그룹에 값을 설정합니다.
    PDF 뷰어가 template.xml의 라디오 버튼 그룹을 읽을 수 있으므로 여기에도 값을 설정합니다.
    """
    template_bytes = read_template_from_pdf(pdf_path)
    if not template_bytes:
        return
    
    try:
        template_root = parse_xml(template_bytes)
        
        # base_tag 찾기
        base_node = None
        for sf in template_root.findall(".//{*}subform"):
            name = sf.get("name")
            if name == base_tag:
                base_node = sf
                break
        
        if base_node is None:
            return
        
        # base_node가 비어있는지 확인 (len() 대신 직접 확인)
        try:
            # lxml Element의 경우 직접 자식 확인
            first_child = next(iter(base_node), None)
            if first_child is None:
                return
        except (TypeError, AttributeError, StopIteration):
            return
        
        # JSON 데이터에서 라디오 버튼 필드 찾기
        target_data = data.get(base_tag, data) if base_tag in data else data
        
        # 라디오 버튼 필드만 처리
        for json_path, type_info in field_type_map.items():
            if type_info.get("type") == "radio":
                options = type_info.get("options", [])
                if not options:
                    continue
                
                # JSON 경로에서 값 가져오기
                path_parts = json_path.split(".")
                if path_parts[0] != base_tag:
                    continue
                
                # 데이터에서 값 찾기
                cur = target_data
                for part in path_parts[1:]:
                    # 배열 인덱스 처리
                    if "[" in part and "]" in part:
                        tag_name = part.split("[")[0]
                        idx = int(part.split("[")[1].split("]")[0])
                        if isinstance(cur, dict) and tag_name in cur:
                            arr = cur[tag_name]
                            if isinstance(arr, list) and idx < len(arr):
                                cur = arr[idx]
                            else:
                                cur = None
                                break
                    else:
                        if isinstance(cur, dict) and part in cur:
                            cur = cur[part]
                        else:
                            cur = None
                            break
                
                if cur is None:
                    continue
                
                value = str(cur) if cur is not None else ""
                
                # 라디오 버튼 그룹의 xfa_path 찾기
                xfa_path = field_xpath_map.get(json_path)
                if not xfa_path:
                    # 부모 경로에서 찾기
                    parent_path = ".".join(path_parts[:-1])
                    xfa_path = field_xpath_map.get(parent_path)
                    if not xfa_path:
                        xfa_path = _json_path_to_xfa_path(parent_path, base_tag, field_xpath_map)
                
                if xfa_path:
                    # 값 변환
                    converted_value = _convert_value_for_field(value, type_info)
                    
                    # 옵션 선택
                    selected_option = None
                    if converted_value in options:
                        selected_option = converted_value
                    else:
                        # 숫자 인덱스인 경우 옵션 이름으로 변환
                        try:
                            idx = int(converted_value) if converted_value else -1
                            if 1 <= idx <= len(options):  # 1-based 인덱스
                                selected_option = options[idx - 1]
                            elif 0 <= idx < len(options):  # 0-based 인덱스
                                selected_option = options[idx]
                        except (ValueError, TypeError):
                            pass
                        
                        # 숫자가 아니면 다른 변환 시도
                        if not selected_option:
                            value_map = {"Y": "Yes", "N": "No", "1": "Yes", "0": "No"}
                            if converted_value in value_map and value_map[converted_value] in options:
                                selected_option = value_map[converted_value]
                            elif options:
                                for opt in options:
                                    if opt.lower() == converted_value.lower():
                                        selected_option = opt
                                        break
                    
                    if selected_option:
                        # template.xml의 라디오 버튼 그룹에 값 설정
                        # template.xml에서는 옵션 이름을 그대로 사용 (원본 PDF와 동일)
                        option_xpath = f"{xfa_path}/{selected_option}"
                        logger.info(f"template.xml 라디오 버튼 그룹 설정: {json_path} -> {option_xpath} = {selected_option}")
                        set_node(base_node, option_xpath, selected_option)
                        
                        # exclGroup 자체에는 value를 설정하지 않음
                        # XFA 스펙에 따르면 exclGroup은 직접 value 요소를 가질 수 없음
                        # 각 라디오 버튼 옵션 필드에만 값을 설정해야 함
                        
                        # 선택되지 않은 다른 옵션들은 옵션 이름을 그대로 설정 (원본 PDF와 동일하게)
                        # template.xml에서는 모든 옵션에 옵션 이름을 설정
                        for opt in options:
                            if opt != selected_option:
                                other_option_xpath = f"{xfa_path}/{opt}"
                                logger.debug(f"template.xml 선택되지 않은 옵션 설정: {other_option_xpath} = {opt}")
                                set_node(base_node, other_option_xpath, opt)
        
        # template.xml을 PDF에 다시 쓰기
        new_template_xml = serialize_xml(template_root)
        write_template_to_pdf(pdf_path, new_template_xml)
        
    except Exception as e:
        logger.warning(f"template.xml 라디오 버튼 그룹 설정 실패: {e}")
        import traceback
        logger.debug(traceback.format_exc())

def _fill_form_radio_groups(
    pdf_path: Path,
    data: dict,
    base_tag: str,
    field_xpath_map: Dict[str, str],
    field_type_map: Dict[str, Dict]
) -> None:
    """
    form.xml의 라디오 버튼 그룹에 값을 설정합니다.
    datasets.xml에 값을 설정하는 것만으로는 PDF 뷰어에서 라디오 버튼이 선택되지 않을 수 있으므로,
    form.xml의 라디오 버튼 그룹에도 값을 설정합니다.
    """
    from app.services.pdf_extract_service import _read_form_from_pdf
    
    form_bytes = _read_form_from_pdf(pdf_path)
    if not form_bytes:
        return
    
    try:
        form_root = parse_xml(form_bytes)
        
        # base_tag 찾기
        base_node = None
        for sf in form_root.findall(".//{*}subform"):
            name = sf.get("name")
            if name == base_tag:
                base_node = sf
                break
        
        if base_node is None:
            return
        
        # base_node가 비어있는지 확인 (len() 대신 직접 확인)
        try:
            # lxml Element의 경우 직접 자식 확인
            first_child = next(iter(base_node), None)
            if first_child is None:
                return
        except (TypeError, AttributeError, StopIteration):
            return
        
        # JSON 데이터에서 라디오 버튼 필드 찾기
        target_data = data.get(base_tag, data) if base_tag in data else data
        
        # 라디오 버튼 필드만 처리
        for json_path, type_info in field_type_map.items():
            if type_info.get("type") == "radio":
                options = type_info.get("options", [])
                if not options:
                    continue
                
                # JSON 경로에서 값 가져오기
                path_parts = json_path.split(".")
                if path_parts[0] != base_tag:
                    continue
                
                # 데이터에서 값 찾기
                cur = target_data
                for part in path_parts[1:]:
                    # 배열 인덱스 처리
                    if "[" in part and "]" in part:
                        tag_name = part.split("[")[0]
                        idx = int(part.split("[")[1].split("]")[0])
                        if isinstance(cur, dict) and tag_name in cur:
                            arr = cur[tag_name]
                            if isinstance(arr, list) and idx < len(arr):
                                cur = arr[idx]
                            else:
                                cur = None
                                break
                    else:
                        if isinstance(cur, dict) and part in cur:
                            cur = cur[part]
                        else:
                            cur = None
                            break
                
                if cur is None:
                    continue
                
                value = str(cur) if cur is not None else ""
                
                # 라디오 버튼 그룹의 xfa_path 찾기
                xfa_path = field_xpath_map.get(json_path)
                if not xfa_path:
                    # 부모 경로에서 찾기
                    parent_path = ".".join(path_parts[:-1])
                    xfa_path = field_xpath_map.get(parent_path)
                    if not xfa_path:
                        xfa_path = _json_path_to_xfa_path(parent_path, base_tag, field_xpath_map)
                
                if xfa_path:
                    # 값 변환
                    converted_value = _convert_value_for_field(value, type_info)
                    
                    # 옵션 선택
                    selected_option = None
                    if converted_value in options:
                        selected_option = converted_value
                    else:
                        # 숫자 인덱스인 경우 옵션 이름으로 변환
                        try:
                            idx = int(converted_value) if converted_value else -1
                            if 1 <= idx <= len(options):  # 1-based 인덱스
                                selected_option = options[idx - 1]
                            elif 0 <= idx < len(options):  # 0-based 인덱스
                                selected_option = options[idx]
                        except (ValueError, TypeError):
                            pass
                        
                        # 숫자가 아니면 다른 변환 시도
                        if not selected_option:
                            value_map = {"Y": "Yes", "N": "No", "1": "Yes", "0": "No"}
                            if converted_value in value_map and value_map[converted_value] in options:
                                selected_option = value_map[converted_value]
                            elif options:
                                for opt in options:
                                    if opt.lower() == converted_value.lower():
                                        selected_option = opt
                                        break
                    
                    if selected_option:
                        # form.xml의 라디오 버튼 그룹에 값 설정
                        # 선택된 옵션에 "1" 설정
                        option_xpath = f"{xfa_path}/{selected_option}"
                        logger.info(f"form.xml 라디오 버튼 그룹 설정: {json_path} -> {option_xpath} = 1")
                        set_node(base_node, option_xpath, "1")
                        
                        # 라디오 버튼 그룹 자체에도 값 설정 (일부 PDF 뷰어에서 필요)
                        # xfa_path가 라디오 그룹 경로이면 그 경로에도 선택된 옵션 이름 설정
                        try:
                            path_parts_xpath = xfa_path.replace("./", "").split("/")
                            cur_node = base_node
                            for part in path_parts_xpath:
                                children = [c for c in cur_node if c.get("name") == part]
                                if not children:
                                    # c.tag가 문자열인지 확인
                                    children = []
                                    for c in cur_node:
                                        c_tag = c.tag
                                        if not isinstance(c_tag, str):
                                            if hasattr(c_tag, '__call__'):
                                                continue
                                            c_tag = str(c_tag)
                                        if strip_ns(c_tag) == part:
                                            children.append(c)
                                if children:
                                    cur_node = children[0]
                                else:
                                    cur_node = None
                                    break
                            
                            # exclGroup을 찾았지만, exclGroup 자체에는 value를 설정하지 않음
                            # XFA 스펙에 따르면 exclGroup은 직접 value 요소를 가질 수 없음
                            # 각 라디오 버튼 옵션 필드에만 값을 설정해야 함
                        except Exception as e:
                            logger.debug(f"form.xml 라디오 그룹 값 설정 실패: {xfa_path}, {e}")
                        
                        # 선택되지 않은 다른 옵션들은 text 요소 제거 (원본 PDF와 동일하게)
                        for opt in options:
                            if opt != selected_option:
                                other_option_xpath = f"{xfa_path}/{opt}"
                                # value/text 요소를 찾아서 text 요소 제거
                                try:
                                    # 경로로 필드 찾기
                                    path_parts = other_option_xpath.replace("./", "").split("/")
                                    cur = base_node
                                    for part in path_parts:
                                        children = [c for c in cur if c.get("name") == part]
                                        if not children:
                                            children = [c for c in cur if strip_ns(c.tag) == part]
                                        if children:
                                            cur = children[0]
                                        else:
                                            cur = None
                                            break
                                    
                                    if cur is not None and strip_ns(cur.tag) == "field":
                                        # value 요소 찾기
                                        value_parent = cur.find(".//{*}value")
                                        if value_parent is not None:
                                            # text 요소 찾기
                                            value_text = value_parent.find(".//{*}text")
                                            if value_text is not None:
                                                # text 요소 제거 (원본 PDF처럼 text 요소가 없도록)
                                                value_parent.remove(value_text)
                                                logger.debug(f"선택되지 않은 옵션 text 요소 제거: {other_option_xpath}")
                                            # override 속성은 유지
                                            value_parent.set("override", "1")
                                        else:
                                            # value 요소가 없으면 생성 (override 속성만)
                                            from lxml.etree import Element
                                            NS_XFA = "http://www.xfa.org/schema/xfa-form/2.8/"
                                            value_parent = Element(f"{{{NS_XFA}}}value")
                                            value_parent.set("override", "1")
                                            cur.append(value_parent)
                                            logger.debug(f"선택되지 않은 옵션 value 요소 생성 (text 없음): {other_option_xpath}")
                                except Exception as e:
                                    logger.debug(f"선택되지 않은 옵션 처리 실패: {other_option_xpath}, {e}")
        
        # form.xml을 PDF에 다시 쓰기
        new_form_xml = serialize_xml(form_root)
        _write_form_to_pdf(pdf_path, new_form_xml)
        
    except Exception as e:
        logger.warning(f"form.xml 라디오 버튼 그룹 설정 실패: {e}")
        import traceback
        logger.debug(traceback.format_exc())

def _fill_unbound_template_fields(pdf_path: Path, data: dict) -> None:
    """
    template XFA 안에서 bind match="none" 이거나 bind 자체가 없는 field 들을
    JSON 데이터 기반으로 <value><text>에 값 세팅.

    예: IMM_0800.Page1.ContactInformation.Information.TelephoneNo
    """
    template_bytes = read_template_from_pdf(pdf_path)
    if template_bytes is None:
        return

    root = parse_xml(template_bytes)

    # 최상위 subform (IMM_0800) 찾기
    base_sub = None
    base_tag = None
    for sf in root.findall(".//{*}subform"):
        name = sf.get("name")
        if name:
            base_sub = sf
            base_tag = name
            break

    if base_sub is None or base_tag is None:
        return

    def walk(node: LET._Element, path_segments: List[str]):
        for child in node:
            if not isinstance(child.tag, str):
                continue

            lname = LET.QName(child).localname

            if lname == "subform":
                nm = child.get("name")
                if nm:
                    walk(child, path_segments + [nm])
                else:
                    walk(child, path_segments)

            elif lname == "field":
                fname = child.get("name")
                if not fname:
                    continue

                # bind 확인 (match="none" 이거나 bind 없음 → 우리가 직접 채워야 하는 타입)
                bind_el = child.find(".//{*}bind")
                match = bind_el.get("match") if bind_el is not None else None
                if match not in (None, "none"):
                    # datasets 쪽으로 이미 묶여 있는건 여기서 안 건드림
                    continue
                
                # 라디오 버튼 그룹(exclGroup) 내부의 필드는 _fill_template_radio_groups에서 처리하므로 스킵
                parent = child.getparent()
                if parent is not None:
                    try:
                        parent_qname = LET.QName(parent)
                        parent_tag = parent_qname.localname
                    except:
                        parent_tag = parent.tag.split('}')[-1] if '}' in parent.tag else parent.tag
                    
                    if parent_tag == "exclGroup":
                        # 라디오 버튼 그룹 내부 필드는 스킵
                        logger.debug(f"라디오 버튼 그룹 내부 필드 스킵: {fname} (parent: {parent_tag})")
                    continue

                # JSON full path 구성
                # path_segments 예: ["IMM_0800", "Page1", "ContactInformation", "Information"]
                # full_path      예: "IMM_0800.Page1.ContactInformation.Information.TelephoneNo"
                full_path = ".".join(path_segments + [fname])

                # JSON에서 값 찾기
                val = _get_value_by_full_json_path(data, full_path)
                if val is None or val == "":
                    # 없으면 그냥 스킵 (절대 이름으로 덮어쓰지 않기)
                    continue

                # 로그 한 번 찍어서 디버깅에 도움되게
                logger.debug(f"Template field fill: {full_path} -> {val!r}")

                # <value><text> 노드 찾아서 값 세팅
                # 주의: caption 쪽 <value><text>랑 헷갈리지 않게
                # 1) field 바로 아래의 value 먼저 찾아보고
                # 2) 없으면 새로 생성
                value_el = None
                # field 바로 아래 value /text 탐색
                for ve in child.findall("{*}value"):
                    value_el = ve
                    break

                if value_el is None:
                    # 템플릿 네임스페이스 (없으면 XFA 템플릿 ns 그대로 사용)
                    value_el = LET.SubElement(
                        child,
                        "{http://www.xfa.org/schema/xfa-template/2.8/}value"
                    )

                text_el = value_el.find("{*}text")
                if text_el is None:
                    text_el = LET.SubElement(
                        value_el,
                        "{http://www.xfa.org/schema/xfa-template/2.8/}text"
                    )

                text_el.text = val

            else:
                walk(child, path_segments)

    # IMM_0800 기준으로 시작
    walk(base_sub, [base_tag])

    new_template = serialize_xml(root)
    write_template_to_pdf(pdf_path, new_template)