"""Analyseur RTF avec pile d'états — Étapes 2–4."""
from __future__ import annotations

import re
from copy import copy
from typing import List, Optional

from .model import Align, Block, Document, ImageBlock, Paragraph, Span, Table, TableCell, TableRow
from .tokenizer import preprocess_rtf, tokenize

CP1254 = "cp1254"

# Caractères symboliques RTF (apostrophes, guillemets, espaces insécables…)
RTF_SPECIAL: dict[str, str] = {
    "rquote": "\u2019",
    "lquote": "\u2018",
    "rdblquote": "\u201d",
    "ldblquote": "\u201c",
    "bullet": "\u2022",
    "endash": "\u2013",
    "emdash": "\u2014",
    "tab": "\t",
    "~": "\u00a0",
    "_": "\u00a0",
    "-": "\u00ad",
}


class Etat:
    def __init__(self) -> None:
        self.bold = False
        self.italic = False
        self.font_size = 12.0
        self.align = Align.LEFT
        self.in_table = False
        self.skip_depth = 0


def _decode_hex_byte(hex_digits: str) -> str:
    try:
        return bytes.fromhex(hex_digits).decode(CP1254)
    except (ValueError, UnicodeDecodeError):
        return ""


def _decode_text(raw: str) -> str:
    parts: List[str] = []
    i = 0
    while i < len(raw):
        if raw.startswith("\\'", i) and i + 4 <= len(raw):
            parts.append(_decode_hex_byte(raw[i + 2 : i + 4]))
            i += 4
        elif raw[i] == "\\" and i + 1 < len(raw) and raw[i + 1] in "\\{}":
            parts.append(raw[i + 1])
            i += 2
        elif raw[i] == "\r" or raw[i] == "\n":
            i += 1
        else:
            parts.append(raw[i])
            i += 1
    return "".join(parts)


def _parse_control(ctrl: str, state: Etat) -> Optional[str]:
    """Applique un mot de contrôle. Retourne 'par', 'cell', 'row', 'imageN' ou None."""
    ctrl = ctrl.strip()
    if not ctrl.startswith("\\"):
        return None

    img = re.match(r"^\\image(\d+)$", ctrl)
    if img:
        return f"image{img.group(1)}"

    name = ctrl[1:]
    num = ""
    while name and (name[-1].isdigit() or name[-1] == "-"):
        num = name[-1] + num
        name = name[:-1]
    if name.endswith(" "):
        name = name[:-1]

    if name == "b":
        state.bold = num != "0"
    elif name == "i":
        state.italic = num != "0"
    elif name == "fs" and num:
        state.font_size = max(6.0, int(num) / 2.0)
    elif name in ("ql", "qr", "qj", "qc"):
        state.align = {
            "ql": Align.LEFT,
            "qr": Align.RIGHT,
            "qj": Align.JUSTIFY,
            "qc": Align.CENTER,
        }[name]
    elif name == "par":
        return "par"
    elif name == "cell":
        return "cell"
    elif name == "row":
        return "row"
    elif name == "trowd":
        return "trowd"
    elif name == "u" and num:
        code = int(num)
        if code < 0:
            code += 65536
        if code <= 0x10FFFF:
            return f"text:{chr(code)}"
    elif name in RTF_SPECIAL:
        return f"text:{RTF_SPECIAL[name]}"
    elif name == "intbl":
        state.in_table = True
    elif name == "pard":
        state.align = Align.LEFT
        return "pard"
    elif name.startswith("image"):
        suffix = name[5:]
        if suffix.isdigit():
            return f"image{suffix}"
    elif name == "*":
        state.skip_depth += 1
    return None


class RtfParser:
    def __init__(self, images: List[bytes]) -> None:
        self.images = images
        self.stack: List[Etat] = [Etat()]
        self.document = Document()
        self._started = False
        self._para = Paragraph()
        self._span_buf = ""
        self._span_style: Optional[Etat] = None
        self._table: Optional[Table] = None
        self._row: Optional[TableRow] = None
        self._cell = TableCell()
        self._col_twips: List[int] = []
        self._skip_uc_fallback = 0

    @property
    def state(self) -> Etat:
        return self.stack[-1]

    def _flush_span(self) -> None:
        if not self._span_buf:
            return
        st = self._span_style or self.state
        text = _decode_text(self._span_buf)
        if not text:
            self._span_buf = ""
            return
        target = self._cell if self.state.in_table else self._para
        if isinstance(target, TableCell):
            target.spans.append(
                Span(text, bold=st.bold, italic=st.italic, font_size=st.font_size)
            )
            if st.bold:
                target.bold = True
        else:
            target.spans.append(
                Span(text, bold=st.bold, italic=st.italic, font_size=st.font_size)
            )
        self._span_buf = ""
        self._span_style = None

    def _flush_paragraph(self) -> None:
        self._flush_span()
        if self._para.spans:
            self.document.blocks.append(
                Block(kind="paragraph", paragraph=copy_paragraph(self._para))
            )
        self._para = Paragraph(align=self.state.align)

    def _flush_cell(self) -> None:
        self._flush_span()
        if self._row is None:
            self._row = TableRow()
        self._cell.bold = any(s.bold for s in self._cell.spans)
        self._row.cells.append(self._cell)
        self._cell = TableCell()

    def _finish_table(self) -> None:
        if self._table and self._table.rows:
            if self._col_twips:
                widths = [w / 20.0 for w in self._col_twips]
                total = sum(widths) or 1.0
                usable = (
                    self.document.page_width_pt
                    - self.document.margin_left_pt
                    - self.document.margin_right_pt
                )
                self._table.col_widths_pt = [usable * (w / total) for w in widths]
            self.document.blocks.append(Block(kind="table", table=self._table))
        self._table = None
        self._row = None
        self._col_twips = []

    def parse_tokens(self, tokens: List[str]) -> Document:
        for tok in tokens:
            if not self._started:
                if tok in ("\\pard", "\\pard\\plain") or tok.startswith("\\pard"):
                    self._started = True
                else:
                    continue

            if tok == "{":
                self.stack.append(copy(self.state))
                continue
            if tok == "}":
                if len(self.stack) > 1:
                    self.stack.pop()
                continue

            if tok.startswith("\\"):
                if tok.startswith("\\'"):
                    self._span_buf += tok
                    continue

                action = _parse_control(tok, self.state)
                if action and action.startswith("text:"):
                    if not self._span_style:
                        self._span_style = copy(self.state)
                    self._span_buf += action[5:]
                    self._skip_uc_fallback = 1
                    continue
                if action == "pard":
                    continue
                if action == "par":
                    if self.state.in_table:
                        self._flush_cell()
                    else:
                        self._flush_paragraph()
                    continue
                if action == "cell":
                    self._flush_cell()
                    continue
                if action == "row":
                    if self._row and self._row.cells:
                        if self._table is None:
                            self._table = Table()
                        self._table.rows.append(self._row)
                    self._row = TableRow()
                    continue
                if action == "trowd":
                    if self._table is None:
                        self._table = Table()
                    elif self._row and self._row.cells:
                        self._table.rows.append(self._row)
                    self._row = TableRow()
                    self.state.in_table = True
                    self._col_twips = []
                    continue
                if action and action.startswith("image"):
                    if self.state.in_table:
                        self._flush_cell()
                        self._finish_table()
                        self.state.in_table = False
                    else:
                        self._flush_paragraph()
                    idx = int(action[5:])
                    if idx < len(self.images):
                        from PIL import Image
                        import io

                        img = Image.open(io.BytesIO(self.images[idx]))
                        self.document.blocks.append(
                            Block(
                                kind="image",
                                image=ImageBlock(
                                    data=self.images[idx],
                                    width_px=img.width,
                                    height_px=img.height,
                                ),
                            )
                        )
                    continue

                if tok.startswith("\\cellx"):
                    m = re.search(r"-?\d+", tok)
                    if m:
                        self._col_twips.append(int(m.group()))
                    continue

                if self.state.skip_depth > 0:
                    continue

                if tok[1:2].isalpha():
                    self._flush_span()
                continue

            if self.state.skip_depth > 0:
                continue

            if self._skip_uc_fallback > 0 and len(tok) <= 2:
                self._skip_uc_fallback -= 1
                continue

            if not self._span_style:
                self._span_style = copy(self.state)
            self._span_buf += tok

        if self._row and self._row.cells and self._table:
            self._table.rows.append(self._row)
        self._flush_paragraph()
        self._finish_table()
        return self.document


def copy_paragraph(p: Paragraph) -> Paragraph:
    return Paragraph(
        spans=[Span(s.text, s.bold, s.italic, s.font_size) for s in p.spans],
        align=p.align,
    )


def parse_rtf(rtf_source: str) -> Document:
    cleaned, images = preprocess_rtf(rtf_source)
    tokens = list(tokenize(cleaned))
    parser = RtfParser(images)

    # Dimensions page (twips → points)
    pw = re.search(r"\\paperw(-?\d+)", rtf_source)
    ph = re.search(r"\\paperh(-?\d+)", rtf_source)
    ml = re.search(r"\\margl(-?\d+)", rtf_source)
    mr = re.search(r"\\margr(-?\d+)", rtf_source)
    mt = re.search(r"\\margt(-?\d+)", rtf_source)
    mb = re.search(r"\\margb(-?\d+)", rtf_source)

    doc = parser.parse_tokens(tokens)
    if pw:
        doc.page_width_pt = int(pw.group(1)) / 20.0
    if ph:
        doc.page_height_pt = int(ph.group(1)) / 20.0
    if ml:
        doc.margin_left_pt = int(ml.group(1)) / 20.0
    if mr:
        doc.margin_right_pt = int(mr.group(1)) / 20.0
    if mt:
        doc.margin_top_pt = int(mt.group(1)) / 20.0
    if mb:
        doc.margin_bottom_pt = int(mb.group(1)) / 20.0
    return doc
