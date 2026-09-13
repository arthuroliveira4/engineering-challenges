#!/usr/bin/env python3
"""Render every value in results.json back onto the page it was read from.

    python verify.py                      # one sheet per company, into verify/
    python verify.py --siren 328024377    # just one

Grounding is the part of this challenge that cannot be checked by a schema:
results.json can be perfectly valid and point at the wrong number. The only
way to know is to look, so this crops the row each value was read from, draws
the submitted box on it, and captions it with the field and the figure we
claim. Anything misaligned is obvious at a glance, and so is anything that
landed on the prior-year column instead of the current one.
"""

from __future__ import annotations

import argparse
import json
import os

import pymupdf
from PIL import Image, ImageDraw

DPI = 150                     # readable without being enormous
MARGIN_ROWS = 1.6             # vertical context, in multiples of the box height
CAPTION_H = 34
COLOURS = {True: (200, 30, 30), False: (200, 30, 30)}


def _font():
    from PIL import ImageFont
    for name in ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, 19)
        except OSError:
            continue
    return ImageFont.load_default()


def _rotation_of(pdf_path: str, page: int) -> int:
    """How far this page is printed sideways, per the pipeline's own detector."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from pipeline.ocr_rows import detect_rotation, load_page

    siren = pdf_path.split("/")[1]
    doc_id = os.path.basename(pdf_path).replace(".pdf", "").rsplit("_", 1)[1]
    try:
        return detect_rotation(load_page(f"data/{siren}/bilans/ocr/{doc_id}", page))
    except (OSError, KeyError, IndexError):
        return 0


def crop_for(pdf_path: str, field: dict) -> Image.Image:
    """The row this value sits on, with the submitted box drawn on it.

    Sideways pages are turned upright before cropping. The box is computed in
    page coordinates first and rotated with the image, so what you see is
    still exactly the box in results.json -- just readable.
    """
    with pymupdf.open(pdf_path) as doc:
        page = doc[field["page"] - 1]
        pixmap = page.get_pixmap(dpi=DPI)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)

    x0, y0, x1, y1 = field["bbox"]

    rotation = _rotation_of(pdf_path, field["page"])
    if rotation:
        # PIL rotates anticlockwise; the box corners move with it.
        image = image.rotate(-rotation, expand=True)
        if rotation == 90:
            x0, y0, x1, y1 = 1 - y1, x0, 1 - y0, x1
        else:
            x0, y0, x1, y1 = y0, 1 - x1, y1, 1 - x0

    px0, py0 = x0 * image.width, y0 * image.height
    px1, py1 = x1 * image.width, y1 * image.height

    # Keep the whole page width so the French label stays visible beside the
    # figure -- a box on the right number of the wrong row looks correct
    # without it.
    pad = max((py1 - py0) * MARGIN_ROWS, 14)
    top, bottom = max(0, py0 - pad), min(image.height, py1 + pad)
    strip = image.crop((0, int(top), image.width, int(bottom))).convert("RGB")

    draw = ImageDraw.Draw(strip)
    draw.rectangle([px0 - 2, py0 - top - 2, px1 + 2, py1 - top + 2],
                   outline=(200, 30, 30), width=3)
    return strip


def caption(width: int, text: str, sub: str) -> Image.Image:
    band = Image.new("RGB", (width, CAPTION_H), (245, 245, 245))
    draw = ImageDraw.Draw(band)
    draw.text((8, 7), text, fill=(10, 10, 10), font=_font())
    draw.text((width - 8 - draw.textlength(sub, font=_font()), 7), sub,
              fill=(90, 90, 90), font=_font())
    return band


def sheet_for(document: dict) -> Image.Image | None:
    """One tall image: every field of one filing, in order."""
    panels: list[Image.Image] = []
    for field in document["fields"]:
        try:
            strip = crop_for(document["pdf"], field)
        except Exception as exc:                      # noqa: BLE001
            print(f"  ! {field['field_key']}: {exc}")
            continue
        value = field["value"]
        shown = f"{value:,.0f}".replace(",", " ") if abs(value) >= 1 else str(value)
        panels.append(caption(
            strip.width,
            f"{field['field_key'].replace('_FRGAAP', '')}   =   {shown} {field['unit']}",
            f"page {field['page']}   conf {field['confidence']}",
        ))
        panels.append(strip)

    if not panels:
        return None
    width = max(p.width for p in panels)
    sheet = Image.new("RGB", (width, sum(p.height for p in panels) + 8 * len(panels)),
                      (255, 255, 255))
    y = 0
    for panel in panels:
        sheet.paste(panel, (0, y))
        y += panel.height + 8
    return sheet


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results.json")
    ap.add_argument("--out", default="verify")
    ap.add_argument("--siren", help="only this company")
    args = ap.parse_args()

    with open(args.results, encoding="utf-8") as fh:
        data = json.load(fh)

    os.makedirs(args.out, exist_ok=True)
    written = 0
    for document in data["documents"]:
        if args.siren and document["siren"] != args.siren:
            continue
        if not document["fields"]:
            continue
        sheet = sheet_for(document)
        if sheet is None:
            continue
        stem = os.path.basename(document["pdf"]).replace(".pdf", "")
        path = os.path.join(args.out, f"{document['siren']}_{stem[6:16]}.png")
        sheet.save(path)
        print(f"{path}  ({len(document['fields'])} fields)")
        written += 1

    print(f"\n{written} sheets in {args.out}/ — open them and check every red box "
          f"sits on the figure named above it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
