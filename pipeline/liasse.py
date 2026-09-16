"""Read a field by its CERFA line code, where the filing has one.

The liasse fiscale numbers every line it prints. Total equity is DL, share
capital DA, cash CF and CG, net revenue FL, external charges FW. The code is
printed in its own narrow column, immediately left of the figure:

    Capital social ou individuel (   .30 348)      DA     30 348
    x=312                            x=1118        x=1982 x=2213

That is a far better anchor than the wording. It survives the OCR mangling
accents, it does not care that one accountant writes "Total des capitaux
propres" where the form says "TOTAL (I)", and it steps straight past the
"(Dont verse : ...)" parenthetical that prints a decoy figure mid-row.

It only exists on the eight filings that use the official form. The other
seven in scope are laid out by the accountant's own software and carry no
codes at all, so callers fall back to wording plus column calibration there.
328024377 files both ways across its three years, so the layout is a property
of the filing and never of the company.
"""

from __future__ import annotations

import re

# Codes are two characters: two letters, or a digit and a letter.
_CODE = re.compile(r"^[A-Z]{2}$|^[0-9][A-Z]$")

# Ambiguous as codes because they are also ordinary French words or numerals.
_NOT_A_CODE = {"DU", "EN", "ET", "LA", "LE", "DE", "AU", "NO", "ON", "SI"}


def codes_on(row) -> dict[str, float]:
    """Map each CERFA code on this row to the figure printed to its right."""
    from pipeline.numbers import figures_in

    figures = figures_in(row)
    found: dict[str, float] = {}

    for index, cell in enumerate(row.cells):
        token = cell.text.strip().upper().replace(" ", "")
        if not _CODE.match(token) or token in _NOT_A_CODE or index == 0:
            continue
        to_the_right = [(v, cells) for v, cells in figures if cells[0].x0 >= cell.x1]
        if to_the_right:
            value, _ = min(to_the_right, key=lambda pair: pair[1][0].x0 - cell.x1)
            found.setdefault(token, value)
    return found


def find(rows, code: str, column=None):
    """(value, cells) for `code` anywhere on the page, or None.

    Returns the cells as well: provenance is the point, and the box we report
    has to be the figure's, not the code's.

    "Nearest figure to the right" is only the current exercise while that cell
    is filled. A blank one prints nothing, so the nearest figure becomes last
    year's, a column over, and the wrong year is reported under the right code
    with nothing to show for it. 504304205 files no change in raw-materials
    inventory in 2017 and prints FV empty; cost of goods sold came out as
    152 338 - 5 450, the 5 450 being the 2016 figure. Pass `column` -- the
    band a proved figure sits in -- and a code whose own cell is empty reads
    as absent, which is what it is.
    """
    from pipeline.numbers import figures_in

    for row in rows:
        for index, cell in enumerate(row.cells):
            token = cell.text.strip().upper().replace(" ", "")
            # A code is never the leftmost thing on a line -- the wording is.
            # One that leads a row has bled down from the row above during
            # banding, and reading the figure beside it reports a neighbour's
            # number: 'CN Clients et comptes rattaches BX 6 987' gave 6 987 as
            # 504304205's total assets, against a page reading 1 689 390.
            if token != code.upper() or index == 0:
                continue
            to_the_right = [(v, cells) for v, cells in figures_in(row)
                            if cells[0].x0 >= cell.x1]
            if not to_the_right:
                continue
            if column is None:
                return min(to_the_right, key=lambda pair: pair[1][0].x0 - cell.x1)
            inside = [pair for pair in to_the_right if column.contains(pair[1])]
            return min(inside, key=lambda pair: pair[1][0].x0 - cell.x1) if inside else None
    return None


def has_codes(rows, expected: tuple[str, ...]) -> bool:
    """True when this page looks like an official liasse rather than a printout."""
    seen: set[str] = set()
    for row in rows:
        seen.update(codes_on(row))
    return len(seen & set(expected)) >= 2
