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


def wordings_on(row) -> list[tuple[int, str]]:
    """The stretches of wording on a row, cut where figures interrupt them.

    A row is not always one account. A sideways filing prints two columns of
    the statement side by side, and rebuilding the page glues them together:

        Dotations aux amortissements sur immobilisations 275 843 267 890
        CHARGES EXCEPTIONNELLES 115 6 720

    arrives as a single row. Ranking that text whole let "exceptionnelle" --
    a word disqualifying a *different* account, printed in the other half of
    the sheet -- throw away 445070311's depreciation, which the page states
    plainly.

    Figures are where one account's wording ends and the next one's begins, so
    each stretch is judged on its own. Splitting there rather than on cell
    boundaries matters: the OCR breaks wording across cells as it pleases, and
    a prefix test would accept "Dotations aux amortissements" while the
    "exceptionnelles" that disqualifies it sat in the next cell along.

    Each stretch is returned with the index of its last cell, so a caller can
    take the figures that follow the wording it actually matched.
    """
    from pipeline.numbers import looks_numeric

    runs: list[tuple[int, str]] = []
    current: list[str] = []
    for index, cell in enumerate(row.cells):
        if looks_numeric(cell.text):
            if current:
                runs.append((index - 1, " ".join(current)))
                current = []
        else:
            current.append(cell.text)
    if current:
        runs.append((len(row.cells) - 1, " ".join(current)))
    return runs or [(len(row.cells) - 1, row.text)]


def _best_wording(row, label: Label) -> tuple[int, int] | None:
    """(rank, index of the wording's last cell) for the best stretch, or None."""
    scored = [(rank, end) for end, text in wordings_on(row)
              if (rank := label.rank(text)) is not None]
    return min(scored) if scored else None


def best_row(rows, label: Label):
    """The highest-ranked row matching `label`, or None.

    Equal ranks are settled in favour of a row that actually prints figures.
    A section heading is worded like the total that closes it -- 445070311
    heads its equity block "SITUATION NETTE" and ends it "TOTAL situation
    nette : 4 845 839" -- and both match equally well, so the heading won on
    page order and the field came back empty three times over.

    Figureless rows stay eligible rather than being filtered out, because one
    reading depends on them: a headcount stated in prose arrives as a single
    box, "Effectif moyen du personnel 43 personnes", with no numeric cell of
    its own for caller and label alike to find.
    """
    from pipeline.numbers import figures_in

    scored = []
    for order, row in enumerate(rows):
        hit = _best_wording(row, label)
        if hit:
            scored.append((hit[0], 0 if figures_in(row) else 1, order, row))
    if not scored:
        return None
    return min(scored, key=lambda found: found[:3])[3]


TOTAL_EQUITY = Label(
    patterns=(
        r"total\s+(des\s+)?capitaux\s+propres",
        r"^capitaux\s+propres\s+(\(|[ivx]+\b)",     # liasse prints "CAPITAUX PROPRES (I)"
        r"situation\s+nette",
    ),
    forbidden=(r"autres\s+reserves", r"ecart", r"subvention", r"provision"),
)

SHARE_CAPITAL = Label(
    patterns=(
        r"capital\s+social\s+ou\s+individuel",
        r"capital\s+social\b",
        r"capital\s+souscrit\s+et\s+appele",
    ),
    forbidden=(r"non\s+appele", r"capital\s+souscrit\s+non"),
)

CASH = Label(
    patterns=(r"^disponibilites\b", r"\bdisponibilites\b"),
    forbidden=(r"total", r"et\s+divers"),
)

MARKETABLE_SECURITIES = Label(
    patterns=(r"valeurs\s+mobilieres\s+de\s+placement",),
    forbidden=(r"total",),
)


# --- compte de resultat -------------------------------------------------

REVENUE = Label(
    patterns=(r"chiffres?\s+d.affaires\s+nets?", r"montant\s+net\s+du\s+chiffre"),
    forbidden=(r"total\s+des\s+produits", r"%"),
)

EXTERNAL_SERVICES = Label(
    patterns=(r"autres\s+achats\s+et\s+charges\s+externes",),
    forbidden=(r"total",),
)

# The OCR renders "traitements" as "traiternents" on at least one filing --
# rn for m is the classic scan confusion -- so match the stem, not the word.
WAGES = Label(patterns=(r"salaires\s+et\s+trait\w*", r"salaires"),
              forbidden=(r"total",))
SOCIAL_CHARGES = Label(patterns=(r"charges\s+sociales",), forbidden=(r"total",))

DEPRECIATION = Label(
    patterns=(r"dotations?\s+aux\s+amortissements\s+sur\s+immobilisati",
              r"-\s*dotations?\s+aux\s+amortissements",
              r"dotations?\s+aux\s+amortissements"),
    forbidden=(r"exceptionnelle", r"financiere", r"derogatoire", r"total"),
)

FINANCIAL_RESULT = Label(
    patterns=(r"resultat\s+financier",),
    forbidden=(r"courant\s+avant", r"total"),
)

INCOME_TAX = Label(
    patterns=(r"imp[oô]ts?\s+sur\s+les\s+benefices",),
    forbidden=(r"total",),
)

# Cost of goods sold is not printed as a line. It is built from purchases and
# the movement in inventory, per the schema's notes. Production stockee is
# excluded: it is a product of the period, not a purchase -- the same reading
# of notes-over-label_fr applied to BS_CAPITAL_EQUITY and PL_DEPRECIATION.
PURCHASES_GOODS = Label(
    patterns=(r"achats?\s+de\s+marchandises",), forbidden=(r"total", r"variation"))
# The liasse writes "Variation de stock (marchandises)"; the accountant's
# software writes "Variation de stock DE marchandises". Missing the second
# spelling silently understated cost of goods sold, and only looking at the
# rendered page caught it.
STOCK_GOODS = Label(
    patterns=(r"variation\s+de\s+stocks?\s*(?:de[s]?\s+)?[\(\[]?\s*marchandises",),
    forbidden=(r"total",))
PURCHASES_MATERIALS = Label(
    patterns=(r"achats?\s+de\s+mati[eè]res\s+premi",), forbidden=(r"total", r"variation"))
STOCK_MATERIALS = Label(
    patterns=(r"variation\s+de\s+stocks?\s*(?:de[s]?\s+)?[\(\[]?\s*mati[eè]res",),
    forbidden=(r"total",))

AVG_WORKFORCE = Label(
    patterns=(r"effectif\s+moyen\s+du\s+personnel", r"effectif\s+moyen"),
    forbidden=(r"total",),
)


def label_ends_at(row, label: Label) -> int | None:
    """Index of the cell where `label`'s wording finishes on this row.

    Rebuilt rows are not always one account. A sideways filing prints two
    columns of the statement side by side, so a row can read

        RESULTAT D'EXPLOITATION 2 157 428 2 272 901 impots sur les benefices 539 793

    where the wording we matched sits at the *end* and the first figures on
    the row belong to something else entirely. Reading left to right, a figure
    belongs to the label printed to its left -- so callers take only what
    follows this index, and 2 157 428 stops being reported as income tax.

    It reads the same stretches best_row ranks. Walking cumulative prefixes
    instead used to disagree with it: on the row

        TOTAL charges externes 3 251 348 2 881 753 RESULTAT FINANCIER 380 965

    every prefix reaching the wording also carried "TOTAL", which the
    financial result forbids, so no index came back -- and callers read a
    missing index as "no need to filter" and reported 3 251 348.
    """
    hit = _best_wording(row, label)
    return hit[1] if hit else None
