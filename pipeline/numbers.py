"""Read the figures out of a French filing, and repair what the OCR broke.

French accounting prints 3 500 529, with a space every three digits and a
comma for the decimal. Our OCR damages that in a handful of recurring ways,
all visible in this corpus:

    4 823_304          the thousands space read as an underscore
    O 952 242          a leading zero read as the letter O
    7.113 7042 290     two adjacent columns run together
    1 234 )            stray punctuation from the form's rules and boxes

The repairs below are deliberately conservative. A token that still looks
ambiguous after cleaning is dropped rather than guessed: reporting a field we
are unsure of is worse, for this challenge, than omitting it.
"""

from __future__ import annotations

import re

# Digits, plus the characters OCR substitutes for them, plus group separators.
_CONFUSED = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "_": " ", "\u00a0": " "})
_STRIP = re.compile(r"[^\d,.\-\s]")
_GROUPED = re.compile(r"^-?\d{1,3}(?: \d{3})+$")
_PLAIN = re.compile(r"^-?\d+$")
_DECIMAL = re.compile(r"^-?\d+(?: \d{3})*,\d{1,2}$")


def looks_numeric(token: str) -> bool:
    """True when a token is plausibly a figure rather than wording or a code."""
    cleaned = token.translate(_CONFUSED).strip()
    if not cleaned or not any(ch.isdigit() for ch in cleaned):
        return False
    # Liasse line codes (CO, 1A, EE, FW) sit in their own narrow column and are
    # mostly letters; anything with more letters than digits is not a figure.
    letters = sum(ch.isalpha() for ch in token)
    digits = sum(ch.isdigit() for ch in token)
    return digits > letters


def parse(token: str) -> float | None:
    """A single figure, or None when the token cannot be read with confidence."""
    cleaned = _STRIP.sub(" ", token.translate(_CONFUSED))
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
    if not cleaned:
        return None

    negative = cleaned.startswith("-")
    cleaned = cleaned.lstrip("-").strip()

    if _DECIMAL.match(cleaned):
        value = float(cleaned.replace(" ", "").replace(",", "."))
    elif _GROUPED.match(cleaned):
        value = float(cleaned.replace(" ", ""))
    elif _PLAIN.match(cleaned):
        # A bare run of digits is only trustworthy when it is short enough to be
        # a real unseparated figure. Long runs are usually two columns fused.
        if len(cleaned) > 9:
            return None
        value = float(cleaned)
    else:
        return None

    return -value if negative else value


def figures_in(row) -> list[tuple[float, object]]:
    """Every readable figure on a row, left to right, paired with its cell.

    The cell is kept because it carries the box we have to report: provenance
    is the point of the exercise, so a value is never separated from where it
    was read.
    """
    out = []
    for cell in row.cells:
        if not looks_numeric(cell.text):
            continue
        value = parse(cell.text)
        if value is not None:
            out.append((value, cell))
    return out


def _gap(left, right) -> float:
    return right.x0 - left.x1


def figures_in(row, glue: float = 0.8) -> list[tuple[float, list]]:
    """Every figure on a row, left to right, with the cells it was read from.

    The OCR splits a grouped figure at its thousands spaces as often as not:
    "2 031 391" arrives as three boxes reading "2", "031", "391". Those boxes
    touch, while the next column sits a hundred pixels away, so proximity
    tells the two cases apart. `glue` is the largest gap we still treat as one
    figure, as a fraction of the row's line height.

    Cells are returned, not just values, because provenance is the point: the
    box we report has to span exactly the digits we read.
    """
    numeric = [c for c in row.cells if looks_numeric(c.text)]
    if not numeric:
        return []

    heights = sorted(c.height for c in row.cells)
    limit = heights[len(heights) // 2] * glue

    groups: list[list] = [[numeric[0]]]
    for cell in numeric[1:]:
        if _gap(groups[-1][-1], cell) <= limit:
            groups[-1].append(cell)
        else:
            groups.append([cell])

    out = []
    for group in groups:
        value = parse(" ".join(c.text for c in group))
        if value is not None:
            out.append((value, group))
    return out
