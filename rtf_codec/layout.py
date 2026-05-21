"""Moteur de mise en page — Étape 5."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .model import Align, Block, Document, Paragraph, Span, Table

FONT_REGULAR = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_ITALIC = "/System/Library/Fonts/Supplemental/Arial Italic.ttf"
FONT_BOLD_ITALIC = "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf"

_FONTS_REGISTERED = False


@dataclass
class TextRun:
    text: str
    x: float
    y: float
    font_size: float
    bold: bool
    italic: bool
    width: float


@dataclass
class Line:
    runs: List[TextRun] = field(default_factory=list)
    y: float = 0.0
    height: float = 12.0
    align: Align = Align.LEFT


@dataclass
class PlacedImage:
    data: bytes
    x: float
    y: float
    width: float
    height: float


@dataclass
class PlacedTable:
    x: float
    y: float
    col_widths: List[float]
    row_heights: List[float]
    cells: List[List[Tuple[List[str], bool, float]]]


@dataclass
class Page:
    lines: List[Line] = field(default_factory=list)
    images: List[PlacedImage] = field(default_factory=list)
    tables: List[PlacedTable] = field(default_factory=list)


@dataclass
class LayoutResult:
    pages: List[Page] = field(default_factory=list)
    page_width: float = 595.32
    page_height: float = 841.92


def _ensure_layout_fonts() -> None:
    global _FONTS_REGISTERED
    if not _FONTS_REGISTERED:
        pdfmetrics.registerFont(TTFont("Arial", FONT_REGULAR))
        pdfmetrics.registerFont(TTFont("Arial-Bold", FONT_BOLD))
        pdfmetrics.registerFont(TTFont("Arial-Italic", FONT_ITALIC))
        pdfmetrics.registerFont(TTFont("Arial-BoldItalic", FONT_BOLD_ITALIC))
        _FONTS_REGISTERED = True


def measure_text(text: str, size: float, bold: bool, italic: bool) -> float:
    _ensure_layout_fonts()
    if bold and italic:
        font_name = "Arial-BoldItalic"
    elif bold:
        font_name = "Arial-Bold"
    elif italic:
        font_name = "Arial-Italic"
    else:
        font_name = "Arial"
    return pdfmetrics.stringWidth(text, font_name, size)


def _line_height(spans: List[Span]) -> float:
    """Interligne aligné sur \\sl278\\slmult1 (référence v4.pdf)."""
    if not spans:
        return 17.0
    fs = max(s.font_size for s in spans)
    return fs * 1.415 + 0.3


def _paragraph_space_after() -> float:
    """\\sa160 → 8 pt."""
    return 8.0


def _wrap_cell_text(text: str, max_width: float, font_size: float, bold: bool) -> List[str]:
    if not text or max_width <= 0:
        return []
    words = text.replace("\u00a0", " ").split()
    lines: List[str] = []
    current: List[str] = []
    width = 0.0

    def flush() -> None:
        nonlocal current, width
        if current:
            lines.append(" ".join(current))
        current = []
        width = 0.0

    for wi, word in enumerate(words):
        piece = word if wi == len(words) - 1 else word + " "
        w = measure_text(piece, font_size, bold, False)
        if width + w > max_width and current:
            flush()
        current.append(word)
        width += w
    flush()
    return lines or [text]


def _wrap_paragraph(
    para: Paragraph,
    max_width: float,
) -> List[List[Tuple[Span, str]]]:
    """Découpe un paragraphe en lignes de fragments (span, texte)."""
    lines: List[List[Tuple[Span, str]]] = []
    current: List[Tuple[Span, str]] = []
    width = 0.0

    def flush_line() -> None:
        nonlocal current, width
        if current:
            lines.append(current)
        current = []
        width = 0.0

    for span in para.spans:
        text = "".join(c for c in span.text if c.isprintable() or c in "\t\n")
        if len(text) > 8000:
            continue
        words = text.replace("\r", "").replace("\n", " ").split(" ")
        for wi, word in enumerate(words):
            if not word:
                continue
            piece = word if wi == len(words) - 1 else word + " "
            w = measure_text(piece, span.font_size, span.bold, span.italic)
            if width + w > max_width and current:
                flush_line()
            current.append((span, piece))
            width += w

    if current:
        lines.append(current)
    return lines or [[]]


def _justify_extra(line: List[TextRun], max_width: float) -> None:
    if len(line) < 2:
        return
    total = sum(r.width for r in line)
    gap = (max_width - total) / (len(line) - 1)
    if gap <= 0:
        return
    x = line[0].x
    for i, run in enumerate(line):
        run.x = x
        if i < len(line) - 1:
            x += run.width + gap


class LayoutEngine:
    def __init__(self, document: Document) -> None:
        self.doc = document
        self.content_width = (
            document.page_width_pt - document.margin_left_pt - document.margin_right_pt
        )
        self.pages: List[Page] = []
        self._y = 0.0
        self._page_h = document.page_height_pt
        self._margin_top = document.margin_top_pt
        self._margin_bottom = document.margin_bottom_pt
        self._margin_left = document.margin_left_pt

    def _new_page(self) -> None:
        self.pages.append(Page())
        self._y = self._page_h - self._margin_top

    def _ensure_space(self, needed: float) -> None:
        if not self.pages:
            self._new_page()
        if self._y - needed < self._margin_bottom:
            self._new_page()

    def _add_line(self, line: Line) -> None:
        self._ensure_space(line.height)
        line.y = self._y
        for run in line.runs:
            run.y = self._y
        self.pages[-1].lines.append(line)
        self._y -= line.height

    def _layout_paragraph(self, para: Paragraph) -> None:
        wrapped = _wrap_paragraph(para, self.content_width)
        for line_idx, fragments in enumerate(wrapped):
            runs: List[TextRun] = []
            x = self._margin_left
            max_size = 12.0
            for span, piece in fragments:
                w = measure_text(piece, span.font_size, span.bold, span.italic)
                runs.append(
                    TextRun(
                        text=piece,
                        x=x,
                        y=0.0,
                        font_size=span.font_size,
                        bold=span.bold,
                        italic=span.italic,
                        width=w,
                    )
                )
                x += w
                max_size = max(max_size, span.font_size)

            line = Line(
                runs=runs,
                y=0.0,
                height=_line_height([s for s, _ in fragments]),
                align=para.align,
            )

            if para.align == Align.RIGHT:
                total = sum(r.width for r in runs)
                offset = self._margin_left + self.content_width - total
                for r in runs:
                    r.x += offset - self._margin_left
            elif para.align == Align.CENTER:
                total = sum(r.width for r in runs)
                offset = (self.content_width - total) / 2
                for r in runs:
                    r.x += offset
            elif para.align == Align.JUSTIFY and line_idx < len(wrapped) - 1:
                _justify_extra(runs, self.content_width)

            self._add_line(line)

        if wrapped and wrapped[0]:
            self._y -= _paragraph_space_after()

    def _layout_image(self, data: bytes, w_px: int, h_px: int) -> None:
        target_w = self.content_width
        target_h = target_w * (h_px / w_px)
        self._ensure_space(target_h + 12)
        img_y = self._y - target_h
        self.pages[-1].images.append(
            PlacedImage(
                data=data,
                x=self._margin_left,
                y=img_y,
                width=target_w,
                height=target_h,
            )
        )
        self._y = img_y - 12

    def _layout_table(self, table: Table) -> None:
        ncols = len(table.rows[0].cells) if table.rows else 0
        cols = table.col_widths_pt or [
            self.content_width / max(1, ncols) for _ in range(ncols)
        ]
        cols = cols[:ncols]
        cell_pad = 15.0 / 20.0  # \\trgaph15
        line_step = 17.0
        min_row = max(27.0, table.trrh_twips / 20.0 * 1.6)

        cells_layout: List[List[Tuple[List[str], bool, float]]] = []
        row_heights: List[float] = []

        for row in table.rows:
            if not any("".join(s.text for s in cell.spans).strip() for cell in row.cells):
                continue
            row_cells: List[Tuple[List[str], bool, float]] = []
            max_lines = 1
            for ci, cell in enumerate(row.cells):
                text = "".join(s.text for s in cell.spans).strip()
                fs = max((s.font_size for s in cell.spans), default=12.0)
                col_w = cols[ci] if ci < len(cols) else cols[-1]
                inset = 0.0 if ci == 0 else cell_pad
                lines = _wrap_cell_text(text, col_w - inset - cell_pad, fs, cell.bold)
                max_lines = max(max_lines, len(lines) or 1)
                row_cells.append((lines, cell.bold, fs))
            text_h = max_lines * line_step
            rh = max(min_row, (max_lines - 1) * line_step + 20.0, text_h + 8.0)
            row_heights.append(rh)
            cells_layout.append(row_cells)

        needed = sum(row_heights) + 16
        self._ensure_space(needed)

        table_y = self._y - sum(row_heights)
        self.pages[-1].tables.append(
            PlacedTable(
                x=self._margin_left,
                y=table_y,
                col_widths=cols,
                row_heights=row_heights,
                cells=cells_layout,
            )
        )
        self._y = table_y - 16

    def layout(self) -> LayoutResult:
        for block in self.doc.blocks:
            if block.kind == "paragraph" and block.paragraph:
                self._layout_paragraph(block.paragraph)
            elif block.kind == "image" and block.image:
                self._layout_image(
                    block.image.data, block.image.width_px, block.image.height_px
                )
            elif block.kind == "table" and block.table:
                self._layout_table(block.table)

        if not self.pages:
            self._new_page()

        return LayoutResult(
            pages=self.pages,
            page_width=self.doc.page_width_pt,
            page_height=self.doc.page_height_pt,
        )
