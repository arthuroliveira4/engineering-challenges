"""Turn a shipped OCR page into reading-order rows.

The `ocr` array in the shipped JSON is a flat list of text lines in no
particular order: on some pages every number arrives before any label.
Iterating it as-is pairs a label with whatever number happens to follow,
which fails silently -- the worst kind of failure for this challenge.

Two page-level distortions have to be undone first.

*Rotation.* Some pages are a landscape form printed onto a portrait sheet, so
the text runs sideways. The PDF does not admit this (``page.rotation`` is 0
everywhere in this corpus) and the OCR polygons are stored as axis-aligned
boxes, so their point order carries no direction either. We detect it from the
shape of the boxes -- upright text is wider than it is tall -- and pick the
direction with the accounting convention that labels sit left of figures.
It is not only 820561470: 445070311 has sideways pages too.

*Skew.* A crooked scan (820561470 averages 0.7 degrees) shifts y by ~30px
across the width of an A4 at 300 dpi, which is taller than a row, so banding
on raw y would interleave neighbouring rows.

Coordinates stay in the shipped convention (pixels at 300 dpi) throughout, and
every transform is recorded so a box can be mapped back to the original page.
Normalising early and carrying fractions around is how you end up with boxes
that are subtly wrong everywhere.
"""

from __future__ import annotations

import json
import math
import os
import re
import statistics
from dataclasses import dataclass, field

# Candidate page rotations, as functions on a point. Keys are the rotation we
# would have to apply to the page to make the text upright.
_ROTATIONS = {
    0: lambda x, y: (x, y),
    90: lambda x, y: (-y, x),
    -90: lambda x, y: (y, -x),
}

_STARTS_WITH_LETTER = re.compile(r"^[^\W\d_]", re.UNICODE)


@dataclass
class Cell:
    """One OCR line, as an axis-aligned box in the working frame."""
    text: str
    score: float
    x0: float
    y0: float
    x1: float
    y1: float
    source: dict = field(default_factory=dict, repr=False)

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass
class Row:
    """Cells sharing a visual line, ordered left to right."""
    cells: list[Cell] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(c.text for c in self.cells)

    @property
    def y(self) -> float:
        return sum((c.y0 + c.y1) / 2 for c in self.cells) / len(self.cells)


def load_page(ocr_dir: str, page: int) -> dict:
    with open(os.path.join(ocr_dir, f"page_{page:03d}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _boxes(page_json: dict, rotation: int, skew: float):
    """Project every OCR polygon into the working frame, as min/max boxes.

    A polygon on a crooked page is not axis-aligned, so min/max over its four
    points is the tightest honest box available -- the same choice
    tools/bbox_viewer.py makes, which keeps our boxes comparable to theirs.
    """
    rotate = _ROTATIONS[rotation]
    pts = [rotate(x, y) for line in page_json["ocr"] for x, y in line["polygon"]]
    if not pts:
        return []
    cx = (min(p[0] for p in pts) + max(p[0] for p in pts)) / 2
    cy = (min(p[1] for p in pts) + max(p[1] for p in pts)) / 2
    a = math.radians(-skew)
    cos_a, sin_a = math.cos(a), math.sin(a)

    out = []
    for line in page_json["ocr"]:
        text = line["text"].strip()
        if not text:
            continue
        flat = []
        for x, y in line["polygon"]:
            rx, ry = rotate(x, y)
            dx, dy = rx - cx, ry - cy
            flat.append((cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a))
        xs = [p[0] for p in flat]
        ys = [p[1] for p in flat]
        out.append(Cell(text, line.get("score", 0.0),
                        min(xs), min(ys), max(xs), max(ys), source=line))
    return out


def _band(cells: list[Cell], tolerance: float) -> list[Row]:
    heights = sorted(c.height for c in cells)
    band = max(statistics.median(heights) * tolerance, 1.0)
    rows: list[Row] = []
    for cell in sorted(cells, key=lambda c: (c.y0 + c.y1) / 2):
        centre = (cell.y0 + cell.y1) / 2
        if rows and abs(centre - rows[-1].y) <= band:
            rows[-1].cells.append(cell)
        else:
            rows.append(Row([cell]))
    for row in rows:
        row.cells.sort(key=lambda c: c.x0)
    return rows


def _label_first_score(rows: list[Row]) -> float:
    """Fraction of multi-cell rows whose leftmost cell reads as a label.

    In a bilan the wording sits left of the figures, so the correct
    orientation is the one that puts letters first in most rows.
    """
    multi = [r for r in rows if len(r.cells) > 1]
    if not multi:
        return 0.0
    return sum(bool(_STARTS_WITH_LETTER.match(r.cells[0].text)) for r in multi) / len(multi)


def detect_rotation(page_json: dict) -> int:
    """0 if the text is already upright, otherwise 90 or -90."""
    upright = _boxes(page_json, 0, 0.0)
    words = [c for c in upright if len(c.text) > 3]
    if not words:
        return 0
    if statistics.median(c.height for c in words) <= statistics.median(c.width for c in words):
        return 0
    return max((90, -90), key=lambda r: _label_first_score(_band(_boxes(page_json, r, 0.0), 0.6)))


def rows_of(page_json: dict, tolerance: float = 0.6) -> list[Row]:
    """Rebuild the page as rows, undoing rotation and skew first."""
    rotation = detect_rotation(page_json)
    skew = page_json.get("skew_angle") or 0.0
    cells = _boxes(page_json, rotation, skew)
    return _band(cells, tolerance) if cells else []
