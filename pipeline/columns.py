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


def calibrate_by_identity(rows, tolerance: float = 2.0) -> Column | None:
    """Find the net column on a bilan actif without a known figure to anchor on.

    Normally the current-year column is located by the one value already
    proved -- total assets, checked against total liabilities. When that check
    fails and the figure is withheld, everything else on the page loses its
    calibration too, and falling back to "the first figure after the label"
    reads the gross column: on the actif, gross is printed first. That is how
    445070311's 2025 cash came out as 8 093 343 against a page supporting
    8 024 487 -- gross securities instead of net.

    The page can calibrate itself instead. Every line of a bilan actif
    satisfies gross - depreciation = net, so any row of three figures where
    that holds reveals where the net column sits. We take the widest
    agreement across the page rather than the first hit, since a coincidence
    can satisfy the identity once but rarely twice in the same place.
    """
    from collections import Counter

    from pipeline.numbers import figures_in

    votes: Counter = Counter()
    boxes: dict = {}
    for row in rows:
        figures = figures_in(row)
        if len(figures) < 3:
            continue
        (gross, _), (depreciation, _), (net, cells) = figures[0], figures[1], figures[2]
        if abs(gross - depreciation - net) > tolerance or net == 0:
            continue
        key = round(cells[0].x0 / 25)          # tolerate ragged right alignment
        votes[key] += 1
        boxes.setdefault(key, Column(cells[0].x0, cells[-1].x1))

    if not votes:
        return None
    best, count = votes.most_common(1)[0]
    return boxes[best] if count >= 2 else None
