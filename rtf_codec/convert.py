"""Pipeline RTF → PDF : tokenizer → parser → layout → PDF."""
from __future__ import annotations

from pathlib import Path

from .layout import LayoutEngine
from .parser import parse_rtf
from .pdf_writer import PdfWriter


def convert_rtf_to_pdf(rtf_path: str | Path, pdf_path: str | Path) -> Path:
    rtf_path = Path(rtf_path)
    pdf_path = Path(pdf_path)
    source = rtf_path.read_text(encoding="latin-1", errors="replace")
    document = parse_rtf(source)
    layout = LayoutEngine(document).layout()
    pdf_bytes = PdfWriter().write(layout)
    pdf_path.write_bytes(pdf_bytes)
    return pdf_path
