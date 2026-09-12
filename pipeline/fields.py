"""Extract one field from one filing, by whichever route the filing supports.

Two routes, tried in order:

1.  the CERFA line code (DL, DA, CG ...), exact and accent-proof, available on
    the filings that use the official liasse;
2.  the French wording plus a calibrated column, for the filings laid out by
    the accountant's own software, which carry no codes at all.

Where both are available they agree -- total liabilities reads 4 823 303 by
code EE and by wording on 328024377 -- which is the closest thing to a second
opinion this challenge offers.

Every result carries the cells it was read from, because the box we report has
to span the digits we actually used, and a value whose provenance we cannot
state is a value we should not be submitting.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline import liasse
from pipeline.columns import Column, pick
from pipeline.labels import Label, best_row, label_ends_at
from pipeline.numbers import figures_in


@dataclass
class Reading:
    """A figure, where it was read, and how confident we are in it."""
    value: float
    cells: list
    page: int
    via: str                      # "code DL" or "label" -- reported in the README
    confidence: float

    @property
    def bbox_px(self) -> tuple[float, float, float, float]:
        return (min(c.x0 for c in self.cells), min(c.y0 for c in self.cells),
                max(c.x1 for c in self.cells), max(c.y1 for c in self.cells))


@dataclass(frozen=True)
class Field:
    """How to find one of the twelve, by either route."""
    key: str
    code: str | None              # CERFA line code, when the form prints one
    label: Label | None


def read(field: Field, rows, page: int, column: Column | None) -> Reading | None:
    """Best available reading of `field` on this page, or None to omit it.

    Returning None is a real answer here: the schema says to omit a field that
    is genuinely absent rather than report zero, and the brief prefers six
    fields done well to twelve with three quietly wrong.
    """
    if field.code:
        hit = liasse.find(rows, field.code)
        if hit:
            value, cells = hit
            return Reading(value, cells, page, f"code {field.code}", 0.95)

    if field.label:
        row = best_row(rows, field.label)
        if row:
            # Only figures printed after the wording can belong to it. On the
            # sideways filings a rebuilt row spans two columns of the
            # statement, and without this the first figure on the row -- which
            # belongs to whatever account was printed to the left -- gets
            # reported under our label.
            end = label_ends_at(row, field.label)
            figures = [(value, cells) for value, cells in figures_in(row)
                       if end is None or cells[0].x0 >= row.cells[end].x1]
            if column:
                chosen = pick(figures, column)
                if chosen:
                    return Reading(chosen[0], chosen[1], page, "label+column", 0.80)
            # No calibration available: the leftmost figure after the wording
            # is the current exercise on every layout in this corpus, but say
            # so at a lower confidence than a coded read.
            if figures:
                return Reading(figures[0][0], figures[0][1], page, "label only", 0.55)
    return None


def calibration(rows, anchor: float) -> Column | None:
    """Locate the current-year column from a figure already proved correct."""
    for row in rows:
        for value, cells in figures_in(row):
            if value == anchor:
                return Column(cells[0].x0, cells[-1].x1)
    return None
