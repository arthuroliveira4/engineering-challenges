"""Convert a box we read into the box the challenge asks us to submit.

The OCR ships pixels at 300 dpi; submissions are fractions of the page, 0-1,
origin top-left. The page size comes from the PDF, in points at 72 dpi, so the
conversion is a scale of 300/72 -- the same arithmetic tools/bbox_viewer.py
does, deliberately, so our boxes can be checked against theirs with --grep.

One trap of our own making: ocr_rows works in a frame it rotated and
de-skewed, and a box measured there would point at the wrong part of the page.
Every cell keeps the OCR line it came from, so boxes are always taken from the
original polygons, never from the working coordinates.
"""

from __future__ import annotations

import functools

import pymupdf

DPI_OF_OCR = 300
POINTS_PER_INCH = 72


@functools.lru_cache(maxsize=64)
def page_size_px(pdf_path: str, page: int) -> tuple[float, float]:
    """Page width and height in 300-dpi pixels, 1-indexed.

    `rect`, not `mediabox`: the two differ on a page carrying /Rotate, and
    every page of 401009741's 2025 filing carries /Rotate 270. Its mediabox is
    841 x 595 while the page as rendered -- and as the OCR measured it, up to
    (2416, 3479) -- is 595 x 841. Normalising by the mediabox divided x by the
    height and y by the width, which put every box on that filing somewhere
    else on the page, two of them clamped flat against the bottom edge.
    tools/bbox_viewer.py reads page.rect for the same reason, so this also
    keeps our boxes checkable against theirs.
    """
    with pymupdf.open(pdf_path) as doc:
        rect = doc[page - 1].rect
    scale = DPI_OF_OCR / POINTS_PER_INCH
    return rect.width * scale, rect.height * scale


def normalise_box(cells, pdf_path: str, page: int) -> list[float]:
    """[x0, y0, x1, y1] in 0-1, spanning exactly the digits we read.

    Boxes come from `cell.source`, the untouched OCR line, so the result is in
    the page's own coordinates however much ocr_rows had to move things to
    read them. A polygon on a crooked page is not axis-aligned, so min/max over
    its corners is the tightest honest box available.
    """
    points = [p for cell in cells for p in cell.source["polygon"]]
    width, height = page_size_px(pdf_path, page)

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    box = [min(xs) / width, min(ys) / height, max(xs) / width, max(ys) / height]
    # Clamp: a box that starts in the margin can round a hair below zero, and
    # the schema rejects anything outside 0-1.
    return [round(min(max(v, 0.0), 1.0), 4) for v in box]
