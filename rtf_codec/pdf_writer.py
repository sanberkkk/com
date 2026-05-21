"""Moteur de rendu PDF — ReportLab (Unicode/Türkçe) + layout inchangé."""
from __future__ import annotations

import io
from typing import Dict, Tuple

from PIL import Image, ImageFile
from reportlab.lib.utils import ImageReader

ImageFile.LOAD_TRUNCATED_IMAGES = True
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .layout import Align, LayoutResult, Page, PlacedTable, TextRun

FONT_REGULAR = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_ITALIC = "/System/Library/Fonts/Supplemental/Arial Italic.ttf"
FONT_BOLD_ITALIC = "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf"

_FONTS_REGISTERED = False


def _ensure_fonts() -> Dict[Tuple[bool, bool], str]:
    global _FONTS_REGISTERED
    names = {
        (False, False): "Arial",
        (True, False): "Arial-Bold",
        (False, True): "Arial-Italic",
        (True, True): "Arial-BoldItalic",
    }
    paths = {
        (False, False): FONT_REGULAR,
        (True, False): FONT_BOLD,
        (False, True): FONT_ITALIC,
        (True, True): FONT_BOLD_ITALIC,
    }
    if not _FONTS_REGISTERED:
        for key, name in names.items():
            pdfmetrics.registerFont(TTFont(name, paths[key]))
        _FONTS_REGISTERED = True
    return names


def _font_name(run: TextRun) -> str:
    return _ensure_fonts()[(run.bold, run.italic)]


class PdfWriter:
    def write(self, layout: LayoutResult) -> bytes:
        _ensure_fonts()
        buf = io.BytesIO()
        page_size = (layout.page_width, layout.page_height)
        c = canvas.Canvas(buf, pagesize=page_size)

        for page in layout.pages:
            self._draw_page(c, page, layout.page_height)
            c.showPage()

        c.save()
        return buf.getvalue()

    def _draw_line(self, c: canvas.Canvas, line, page_height: float) -> None:
        if not line.runs:
            return
        # layout._y est déjà en coordonnées PDF (origine en bas)
        y = line.y
        styles = {(r.bold, r.italic, r.font_size) for r in line.runs}
        if line.align != Align.JUSTIFY and len(styles) == 1:
            text = "".join(r.text for r in line.runs).replace("\u00a0", " ")
            if not text.strip():
                return
            r0 = line.runs[0]
            c.setFont(_font_name(r0), r0.font_size)
            c.drawString(r0.x, y, text)
            return
        for run in line.runs:
            text = run.text.replace("\u00a0", " ")
            if not text:
                continue
            c.setFont(_font_name(run), run.font_size)
            c.drawString(run.x, y, text)

    def _draw_page(self, c: canvas.Canvas, page: Page, page_height: float) -> None:
        for line in page.lines:
            self._draw_line(c, line, page_height)

        for img in page.images:
            pil_img = Image.open(io.BytesIO(img.data))
            pil_img.load()
            c.drawImage(
                ImageReader(pil_img),
                img.x,
                img.y,
                width=img.width,
                height=img.height,
                preserveAspectRatio=True,
                anchor="sw",
            )

        for table in page.tables:
            self._draw_table(c, table, page_height)

    def _draw_table(self, c: canvas.Canvas, table: PlacedTable, page_height: float) -> None:
        del page_height
        x0 = table.x
        rows = len(table.cells)
        total_w = sum(table.col_widths)
        height = table.row_height * rows
        y_bottom = table.y
        y_top = table.y + height

        c.setLineWidth(0.5)
        c.rect(x0, y_bottom, total_w, height, stroke=1, fill=0)

        cx = x0
        for w in table.col_widths[:-1]:
            cx += w
            c.line(cx, y_bottom, cx, y_top)

        for r in range(1, rows):
            ry = y_bottom + r * table.row_height
            c.line(x0, ry, x0 + total_w, ry)

        for ri, row in enumerate(table.cells):
            cy = y_bottom + (rows - 1 - ri) * table.row_height + 6
            cx = x0 + 4
            for ci, (text, bold) in enumerate(row):
                if text:
                    display = text.replace("\u00a0", " ").rstrip("~ ")
                    c.setFont(
                        _ensure_fonts()[(bold, False)],
                        12,
                    )
                    c.drawString(cx, cy, display)
                if ci < len(table.col_widths):
                    cx += table.col_widths[ci]
