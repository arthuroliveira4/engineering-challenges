"""Work out which column on a statement page holds the current exercise.

A liasse row carries several figures -- gross, depreciation, net, and last
year's net -- and picking the wrong one is a plausible-looking error worth
millions. Position cannot be inferred by counting, because a blank column
prints nothing at all:

    VALEURS MOBILIERES DE PLACEMENT   525      525      259
    Total des capitaux propres        322 009  157 836

Both rows are complete; they have three figures and two. Reading "the third"
would take last year's figure from one and nothing from the other.

The column header would settle it, and on most pages it is there -- Brut,
Amortissements, Net, Net -- but 445070311 prints no header our OCR can see,
and the liasse pages vary between three and four headed columns.

So we calibrate instead, against a figure we have already proved. Total
assets is checked against total liabilities on the facing page, an identity
French law requires, and that check passes on all fifteen filings. Wherever
that verified figure sits horizontally is, by definition, the current-year
column -- and every other row on the page is read from the same band.

This also disentangles the sideways pages, where actif and passif are
printed side by side on one sheet and a rebuilt row spans both: their
current-year columns are in different halves of the page, so selecting by
x separates the two statements without any extra rule.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    """The horizontal band a statement's current-year figures sit in."""
    x0: float
    x1: float

    @property
    def centre(self) -> float:
        return (self.x0 + self.x1) / 2

    def contains(self, cells) -> bool:
        centre = (cells[0].x0 + cells[-1].x1) / 2
        return self.x0 - self.tolerance <= centre <= self.x1 + self.tolerance

    @property
    def tolerance(self) -> float:
        """Columns are ragged: figures are right-aligned but widths differ."""
        return max((self.x1 - self.x0) * 0.9, 60.0)


def calibrate(row, figures, value: float) -> Column | None:
    """The column holding `value` on `row`, or None if it is not there."""
    for figure_value, cells in figures:
        if figure_value == value:
            return Column(cells[0].x0, cells[-1].x1)
    return None


def pick(figures, column: Column):
    """The figure from `figures` sitting in `column`, or None.

    Ties are broken by distance to the column centre rather than by order, so
    a stray figure bleeding in from a neighbouring column does not win just
    by being first.
    """
    inside = [(value, cells) for value, cells in figures if column.contains(cells)]
    if not inside:
        return None
    return min(inside, key=lambda pair: abs(
        (pair[1][0].x0 + pair[1][-1].x1) / 2 - column.centre))
