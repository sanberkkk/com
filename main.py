#!/usr/bin/env python3
"""
Convertisseur RTF → PDF — PROJET SEMESTRIEL

Architecture :
  Octets RTF → Tokenizer → Analyseur RTF → DOM → Mise en page → PDF 1.7

Usage :
  python main.py [entree.rtf] [sortie.pdf]

Par défaut : v4.rtf → v4_out.pdf (chemins Downloads ou répertoire courant).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rtf_codec.convert import convert_rtf_to_pdf


def _default_paths() -> tuple[Path, Path]:
    downloads = Path.home() / "Downloads"
    rtf = downloads / "v4.rtf"
    if not rtf.exists():
        rtf = Path("v4.rtf")
    pdf = rtf.with_name("v4_out.pdf")
    return rtf, pdf


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Codec RTF → PDF (projet semestriel)")
    parser.add_argument("input", nargs="?", help="Fichier RTF source")
    parser.add_argument("output", nargs="?", help="Fichier PDF de sortie")
    args = parser.parse_args(argv)

    rtf_path, pdf_path = _default_paths()
    if args.input:
        rtf_path = Path(args.input)
    if args.output:
        pdf_path = Path(args.output)

    if not rtf_path.exists():
        print(f"Erreur : fichier introuvable : {rtf_path}", file=sys.stderr)
        return 1

    convert_rtf_to_pdf(rtf_path, pdf_path)
    print(f"PDF généré : {pdf_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
