"""Tokenizer RTF — Étape 1 du codec."""
from __future__ import annotations

import re
from typing import Generator, Iterable, List, Tuple

TOKEN_RE = re.compile(r"\\[a-zA-Z]+-?\d* ?|\\'[0-9a-fA-F]{2}|[{}]|[^\\{}]+")


def tokenize(rtf: str) -> Generator[str, None, None]:
    """Tokenize RTF selon la spécification du projet."""
    for match in TOKEN_RE.finditer(rtf):
        yield match.group(0)


def extract_jpeg_from_block(block: str) -> bytes | None:
    start = block.lower().find("ffd8ff")
    if start < 0:
        return None
    chunk = block[start:]
    pairs = re.findall(r"[0-9a-fA-F]{2}", chunk, flags=re.I)
    hex_str = "".join(pairs)
    end = hex_str.lower().rfind("ffd9")
    if end < 0:
        return None
    hex_str = hex_str[: end + 4]
    if len(hex_str) % 2:
        hex_str = hex_str[:-1]
    return bytes.fromhex(hex_str)


def _strip_group(rtf: str, opener: str) -> str:
    """Supprime un groupe RTF commençant par opener (ex. '{\\fonttbl')."""
    out: List[str] = []
    i = 0
    n = len(rtf)
    while i < n:
        if rtf.startswith(opener, i):
            depth = 0
            j = i
            while j < n:
                if rtf[j] == "{":
                    depth += 1
                elif rtf[j] == "}":
                    depth -= 1
                    if depth == 0:
                        i = j + 1
                        break
                j += 1
            else:
                out.append(rtf[i])
                i += 1
        else:
            out.append(rtf[i])
            i += 1
    return "".join(out)


def preprocess_rtf(rtf: str) -> Tuple[str, List[bytes]]:
    """Extrait les images binaires et remplace les blocs \\pict par des marqueurs."""
    images: List[bytes] = []
    out: List[str] = []
    i = 0
    n = len(rtf)
    marker = "{\\*\\shppict"

    while i < n:
        if rtf.startswith(marker, i):
            depth = 0
            j = i
            while j < n:
                ch = rtf[j]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        block = rtf[i : j + 1]
                        blob = extract_jpeg_from_block(block)
                        if blob:
                            idx = len(images)
                            images.append(blob)
                            out.append(f"\\image{idx} ")
                        i = j + 1
                        break
                j += 1
            else:
                out.append(rtf[i])
                i += 1
        else:
            out.append(rtf[i])
            i += 1

    text = "".join(out)
    for marker in ("{\\*\\themedata", "{\\*\\datastore"):
        pos = text.find(marker)
        if pos >= 0:
            text = text[:pos]
    for opener in (
        "{\\fonttbl",
        "{\\colortbl",
        "{\\stylesheet",
        "{\\*\\themedata",
        "{\\*\\colorschememapping",
        "{\\*\\latentstyles",
        "{\\nonshppict",
        "{\\pict",
        "{\\*\\shppict",
    ):
        while opener in text:
            text = _strip_group(text, opener)
    return text, images
