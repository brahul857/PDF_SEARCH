from pathlib import Path
from typing import Any, Dict, List, Union
from functools import lru_cache

import pymupdf
import re


@lru_cache(maxsize=1)
def _ocr_engine():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def _ocr_image(image_bytes: bytes) -> str:
    """OCR one page image with a portable ONNX-based engine."""
    try:
        result, _ = _ocr_engine()(image_bytes)
    except ImportError:
        return ""
    except Exception:
        return ""

    if not result:
        return ""

    lines = []
    for item in result:
        if len(item) >= 2 and item[1]:
            box = item[0]
            top = min(float(point[1]) for point in box)
            left = min(float(point[0]) for point in box)
            lines.append((top, left, str(item[1]).strip()))

    lines.sort(key=lambda line: (line[0], line[1]))
    return "\n".join(text for _, _, text in lines)


def extract_pdf_pages(
    source: Union[bytes, bytearray, Path, str],
    *,
    ocr: bool = True,
    minimum_text_chars: int = 40,
) -> List[Dict[str, Any]]:
    """Extract PDF text, falling back to OCR for image-only or sparse pages."""
    if isinstance(source, (bytes, bytearray)):
        document = pymupdf.open(stream=bytes(source), filetype="pdf")
    else:
        document = pymupdf.open(str(source))

    pages: List[Dict[str, Any]] = []
    try:
        for page_number, page in enumerate(document, start=1):
            text = page.get_text("text") or ""
            text = text.strip()

            if ocr and len(text) < minimum_text_chars:
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
                text = _ocr_image(pixmap.tobytes("png"))

            pages.append({"page": page_number, "text": text})
    finally:
        document.close()
    return pages


def extract_template_field_value(
    source: Union[List[Dict[str, Any]], str],
    field_name: str,
) -> str:
    """Extract the value following a template field name."""
    if isinstance(source, str):
        text_by_page = [(1, source)]
    else:
        text_by_page = [
            (item.get("page", page_number), str(item.get("text", "")))
            for page_number, item in enumerate(source, start=1)
        ]

    pattern = re.compile(
        rf"(?im)^\s*{re.escape(field_name.strip())}\s*[:\-]?\s*(.*)$",
    )
    for _, text in text_by_page:
        lines = text.splitlines()
        for index, line in enumerate(lines):
            line = re.sub(r"\s+", " ", line).strip()
            match = pattern.match(line)
            if not match:
                continue

            value = match.group(1).strip(" \t:-")
            if not value and index + 1 < len(lines):
                value = re.sub(r"\s+", " ", lines[index + 1]).strip()
            if value:
                return value
    return ""
