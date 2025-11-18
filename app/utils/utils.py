from __future__ import annotations
from pathlib import Path
import pikepdf
from lxml import etree

NS = {"xfa": "http://www.xfa.org/schema/xfa-data/1.0/"}

def _get_xfa(pdf: pikepdf.Pdf):
	acro = pdf.Root.get("/AcroForm", None)
	if acro is None or "/XFA" not in acro:
		raise RuntimeError("XFA 엔트리를 찾지 못했습니다. (XFA 폼 아님 또는 평탄화됨)")
	return acro["/XFA"]

def read_datasets_from_pdf(pdf_path: str | Path) -> bytes:
	"""PDF에서 XFA datasets XML을 추출합니다."""
	with pikepdf.open(str(pdf_path)) as pdf:
		xfa = _get_xfa(pdf)
		if isinstance(xfa, pikepdf.Array):
			for i in range(0, len(xfa), 2):
				if isinstance(xfa[i], pikepdf.String) and str(xfa[i]).lower() == "datasets":
					return bytes(xfa[i+1].read_bytes())
			raise RuntimeError("XFA 배열에서 'datasets' 패킷을 찾지 못했습니다.")
		elif isinstance(xfa, pikepdf.Stream):
			return bytes(xfa.read_bytes())
		else:
			raise RuntimeError("알 수 없는 XFA 형식입니다.")

def read_template_from_pdf(pdf_path: str | Path) -> bytes | None:
	"""PDF에서 XFA template XML을 추출합니다."""
	with pikepdf.open(str(pdf_path)) as pdf:
		xfa = _get_xfa(pdf)
		if isinstance(xfa, pikepdf.Array):
			for i in range(0, len(xfa), 2):
				if isinstance(xfa[i], pikepdf.String) and str(xfa[i]).lower() == "template":
					return bytes(xfa[i+1].read_bytes())
			return None
		elif isinstance(xfa, pikepdf.Stream):
			# 단일 스트림인 경우 template이 별도로 없을 수 있음
			return None
		else:
			return None

def write_datasets_to_pdf(pdf_in: str | Path, datasets_xml: bytes, pdf_out: str | Path):
	"""PDF에 XFA datasets XML을 주입합니다."""
	with pikepdf.open(str(pdf_in)) as pdf:
		acro = pdf.Root.get("/AcroForm", None)
		if acro is None or "/XFA" not in acro:
			raise RuntimeError("XFA 엔트리를 찾지 못했습니다.")
		xfa = acro["/XFA"]
	
		if isinstance(xfa, pikepdf.Array):
			# 배열: ["config", stream, "template", stream, "datasets", stream, ...]
			replaced = False
			for i in range(0, len(xfa), 2):
				name = xfa[i]
				if isinstance(name, pikepdf.String) and str(name).lower() == "datasets":
					# 새 스트림 생성 후 교체
					new_stream = pikepdf.Stream(pdf, datasets_xml)
					new_stream["/Subtype"] = pikepdf.Name("/XML")
					xfa[i + 1] = new_stream
					replaced = True
					break
			if not replaced:
				raise RuntimeError("XFA 배열에서 'datasets' 패킷을 찾지 못했습니다.")
	
		elif isinstance(xfa, pikepdf.Stream):
			# 단일 스트림: /AcroForm /XFA 자체를 새 스트림으로 대체
			new_stream = pikepdf.Stream(pdf, datasets_xml)
			new_stream["/Subtype"] = pikepdf.Name("/XML")
			acro["/XFA"] = new_stream
		else:
			raise RuntimeError("알 수 없는 XFA 형식입니다.")
	
		# 뷰어가 외형 재생성하도록 힌트
		acro["/NeedAppearances"] = True
	
		pdf.save(str(pdf_out), static_id=True, linearize=False)

def strip_ns(tag: str) -> str:
	"""XML 태그에서 네임스페이스를 제거합니다."""
	return tag.split("}", 1)[1] if "}" in tag else tag

def parse_xml(xml_bytes: bytes) -> etree._Element:
	"""XML 바이트를 파싱하여 ElementTree Element를 반환합니다."""
	parser = etree.XMLParser(remove_blank_text=True)
	return etree.fromstring(xml_bytes, parser=parser)

def serialize_xml(root: etree._Element) -> bytes:
	"""ElementTree Element를 XML 바이트로 직렬화합니다."""
	return etree.tostring(root, encoding="utf-8", xml_declaration=False, pretty_print=False)

def set_node(form: etree._Element, xpath: str, val: str):
	"""form 요소 내에서 xpath로 노드를 찾아 값을 설정합니다.
	
	Args:
		form: XML 루트 요소 (예: IMM_0800 노드)
		xpath: 상대 경로 (예: "./Page1/ApplyFrom/ApplyFromOpt")
		val: 설정할 값
	"""
	import logging
	logger = logging.getLogger(__name__)
	
	# XPath 표현식 지원 (./로 시작하거나 /를 포함하는 경우)
	if xpath.startswith("./") or "/" in xpath:
		# 상대 경로를 XPath로 변환
		# ./Page1/ApplyFrom/ApplyFromOpt -> .//*[local-name()='Page1']/*[local-name()='ApplyFrom']/*[local-name()='ApplyFromOpt']
		if xpath.startswith("./"):
			rel_path = xpath[2:] if len(xpath) > 2 else ""
		else:
			rel_path = xpath
		
		if rel_path:
			# 경로를 태그로 분리
			path_parts = [p for p in rel_path.split("/") if p]
			if path_parts:
				# 방법 1: 직접 자식 경로 시도 (더 빠르고 정확)
				cur = form
				found = True
				for part in path_parts:
					# 인덱스 처리: Page1[1] -> Page1의 첫 번째
					if "[" in part and "]" in part:
						tag_name = part.split("[")[0]
						idx_str = part.split("[")[1].split("]")[0]
						try:
							idx = int(idx_str) - 1  # 1-based -> 0-based
							children = [c for c in cur if strip_ns(c.tag) == tag_name]
							if idx < len(children):
								cur = children[idx]
							else:
								found = False
								break
						except (ValueError, IndexError):
							found = False
							break
					else:
						# 태그 이름으로 직접 자식 찾기
						children = [c for c in cur if hasattr(c, 'tag') and isinstance(c.tag, str) and strip_ns(c.tag) == part]
						if not children:
							# 태그 이름으로 찾지 못하면 name 속성으로 찾기 (subform, exclGroup 등)
							children = [c for c in cur if c.get("name") == part]
						if children:
							cur = children[0]
						else:
							found = False
							break
				
				if found:
					# field의 경우 value/text 요소에 값을 설정해야 함
					if strip_ns(cur.tag) == "field":
						# value 요소 찾기
						value_parent = cur.find(".//{*}value")
						if value_parent is None:
							# value 요소가 없으면 생성
							from lxml.etree import Element
							NS_XFA_FORM = "http://www.xfa.org/schema/xfa-form/2.8/"
							value_parent = Element(f"{{{NS_XFA_FORM}}}value")
							# override 속성 설정 (PDF 뷰어가 값을 인식하도록)
							value_parent.set("override", "1")
							cur.append(value_parent)
						else:
							# value 요소가 있으면 override 속성도 설정
							value_parent.set("override", "1")
						
						# text 요소 찾기
						value_text = value_parent.find(".//{*}text")
						if value_text is None:
							# text 요소가 없으면 생성
							from lxml.etree import Element
							NS_XFA_FORM = "http://www.xfa.org/schema/xfa-form/2.8/"
							value_text = Element(f"{{{NS_XFA_FORM}}}text")
							value_parent.append(value_text)
						
						value_text.text = "" if val is None else str(val)
						return
					# 일반 노드는 text 직접 설정
					cur.text = "" if val is None else str(val)
					return
				
				# 방법 2: XPath 사용 (하위 모든 곳에서 검색)
				xpath_expr = ".//" + "/".join([f"*[local-name()='{part.split('[')[0]}']" for part in path_parts])
				nodes = form.xpath(xpath_expr)
				if nodes:
					node = nodes[0]
					# field의 경우 value/text 요소에 값을 설정해야 함
					if strip_ns(node.tag) == "field":
						# value 요소 찾기
						value_parent = node.find(".//{*}value")
						if value_parent is None:
							# value 요소가 없으면 생성
							from lxml.etree import Element
							NS_XFA_FORM = "http://www.xfa.org/schema/xfa-form/2.8/"
							value_parent = Element(f"{{{NS_XFA_FORM}}}value")
							# override 속성 설정 (PDF 뷰어가 값을 인식하도록)
							value_parent.set("override", "1")
							node.append(value_parent)
						else:
							# value 요소가 있으면 override 속성도 설정
							value_parent.set("override", "1")
						
						# text 요소 찾기
						value_text = value_parent.find(".//{*}text")
						if value_text is None:
							# text 요소가 없으면 생성
							from lxml.etree import Element
							NS_XFA_FORM = "http://www.xfa.org/schema/xfa-form/2.8/"
							value_text = Element(f"{{{NS_XFA_FORM}}}text")
							value_parent.append(value_text)
						
						value_text.text = "" if val is None else str(val)
						return
					# 일반 노드는 text 직접 설정
					node.text = "" if val is None else str(val)
					return
				else:
					logger.warning(f"노드를 찾을 수 없음: xpath={xpath}, xpath_expr={xpath_expr}")
		
		# 경로를 찾지 못한 경우
		return
	else:
		# 단순 태그 경로인 경우 기존 방식 사용
		node = form.find(xpath, namespaces=NS)
		if node is not None:
			node.text = "" if val is None else str(val)
			return
		else:
			logger.warning(f"노드를 찾을 수 없음 (find 방식): xpath={xpath}")

def write_template_to_pdf(pdf_path: str | Path, template_xml: bytes) -> None:
    """
    /AcroForm /XFA 배열에서 이름에 'template' 이 들어가는 스트림을
    전달받은 XML로 교체해서 PDF 를 덮어쓴다.
    """
    pdf_path = str(pdf_path)

    with pikepdf.Pdf.open(pdf_path, allow_overwriting_input=True) as pdf:
        acro = pdf.Root.get("/AcroForm", None)
        if not acro:
            raise ValueError("AcroForm not found")

        xfa = acro.get("/XFA", None)
        if not xfa:
            raise ValueError("XFA not found")

        if isinstance(xfa, pikepdf.Array):
            parts = list(xfa)
            for i in range(0, len(parts), 2):
                nm = str(parts[i])
                st = parts[i + 1]
                if "template" in nm.lower():
                    # 이 스트림 내용을 새 XML로 교체
                    st_obj = st
                    st_obj.write(template_xml)
                    break
        elif isinstance(xfa, pikepdf.Stream):
            # 단일 XFA 스트림인 경우 전체를 교체
            xfa.write(template_xml)

        pdf.save(pdf_path)