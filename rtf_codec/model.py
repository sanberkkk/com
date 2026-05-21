"""Modèle intermédiaire de document (DOM) — PROJET SEMESTRIEL."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Align(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    CENTER = "center"
    JUSTIFY = "justify"


@dataclass
class Span:
    text: str
    bold: bool = False
    italic: bool = False
    font_size: float = 12.0


@dataclass
class Paragraph:
    spans: List[Span] = field(default_factory=list)
    align: Align = Align.LEFT


@dataclass
class ImageBlock:
    data: bytes
    width_px: int
    height_px: int


@dataclass
class TableCell:
    spans: List[Span] = field(default_factory=list)
    bold: bool = False


@dataclass
class TableRow:
    cells: List[TableCell] = field(default_factory=list)


@dataclass
class Table:
    rows: List[TableRow] = field(default_factory=list)
    col_widths_pt: List[float] = field(default_factory=list)


@dataclass
class Block:
    kind: str  # "paragraph" | "image" | "table"
    paragraph: Optional[Paragraph] = None
    image: Optional[ImageBlock] = None
    table: Optional[Table] = None


@dataclass
class Document:
    blocks: List[Block] = field(default_factory=list)
    page_width_pt: float = 595.32
    page_height_pt: float = 841.92
    margin_left_pt: float = 70.85
    margin_right_pt: float = 70.85
    margin_top_pt: float = 70.85
    margin_bottom_pt: float = 70.85
