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
	"""form 요소 내에서 xpath로 노드를 찾아 값을 설정합니다."""
	node = form.find(xpath, namespaces=NS)
	if node is not None:
		node.text = "" if val is None else str(val)


