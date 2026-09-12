"""Find the row a field is printed on, when several rows almost match.

"TOTAL ACTIF" matches the grand total, but it also matches TOTAL ACTIF
IMMOBILISE and TOTAL ACTIF CIRCULANT one and two rows above it -- subtotals
that are wrong by millions and look entirely plausible in the output. The
same trap exists for most of the twelve fields, because a liasse subtotals
every block it prints.

So a field declares its wording as an ordered list of patterns, best first,
plus the words that disqualify a row outright. We take the best-ranked match
on the page rather than the first or the longest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline.pages import normalise


@dataclass(frozen=True)
class Label:
    """How a field is worded, and what it must not be confused with."""
    patterns: tuple[str, ...]       # ordered, best first
    forbidden: tuple[str, ...] = ()

    def rank(self, text: str) -> int | None:
        """Position in `patterns`, or None when the row does not qualify."""
        flat = normalise(text)
        if any(re.search(bad, flat) for bad in self.forbidden):
            return None
        for i, pattern in enumerate(self.patterns):
            if re.search(pattern, flat):
                return i
        return None


# Subtotals that shadow a grand total on the same page.
_NOT_A_GRAND_TOTAL = (
    r"immobilise", r"circulant", r"non ventile", r"amortissement",
    r"creance", r"stock", r"provision", r"charges? a repartir",
)

TOTAL_ASSETS = Label(
    patterns=(
        r"total\s+gen[ée]ra\w*",      # the liasse wording, and most software
        r"total\s+actif\b",           # 820561470's software says TOTAL ACTIF (I a VI)
        r"total\s+du\s+bilan",
    ),
    forbidden=_NOT_A_GRAND_TOTAL,
)

TOTAL_LIABILITIES = Label(
    patterns=(
        r"total\s+gen[ée]ra\w*",
        r"total\s+passif\b",
        r"total\s+du\s+bilan",
    ),
    forbidden=_NOT_A_GRAND_TOTAL + (r"dettes", r"capitaux"),
)


def best_row(rows, label: Label):
    """The highest-ranked row matching `label`, or None."""
    scored = []
    for row in rows:
        rank = label.rank(row.text)
        if rank is not None:
            scored.append((rank, row))
    if not scored:
        return None
    return min(scored, key=lambda pair: pair[0])[1]
