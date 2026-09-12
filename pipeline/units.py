"""Decide whether a filing states its figures in euros or in thousands.

The brief warns that one company in scope "reports in thousands of euros,
said in passing on a handful of lines", and getting this wrong is a factor of
1000 on every field. The obvious implementation -- grep the document for K€
and believe it -- gets that company backwards.

328024377 says both things, in different places:

    p5   "les montants sont exprimes en euros"                 the accounting policy
    p10  "...participations etrangeres, detenues entre 10 et
          50%, les montants sont indiques en K€"               one annexe schedule

The second governs the tableau des filiales et participations, not the
liasse. Magnitude settles it: total assets read 5 641 580, and the filer is a
Lyon chocolatier -- 5.6 million euros, not 5.6 billion. Its revenue reads
4 982 166, which agrees.

So a declaration is only believed when it governs the page we read from:
one printed on the statement page itself, or a general accounting-policy
statement with no schedule attached to it. Everything else is ignored, and
the CERFA default of euros stands.
"""

from __future__ import annotations

import glob
import json
import os
import re
from dataclasses import dataclass

from pipeline.pages import normalise

EUR = "EUR"
KEUR = "kEUR"
COUNT = "count"

_THOUSANDS = r"(milliers? d.euros?|k\s?€|keur|kilo ?euros?)"
_DECLARES = r"(exprim\w+|indiqu\w+|etabli\w+|presente\w+|chiffres?|montants?|unite)"

_KEUR_CLAIM = re.compile(rf"{_DECLARES}[^.]{{0,40}}\ben\s+{_THOUSANDS}|\ben\s+{_THOUSANDS}\b")
_EUR_CLAIM = re.compile(rf"{_DECLARES}[^.]{{0,40}}\ben\s+euros?\b|\ben\s+euros?\b")

# A unit stated inside one of these schedules governs that schedule alone.
_SCHEDULE = re.compile(
    r"filiale|participation|detenue|societe\w*\s+dont|portefeuille|"
    r"engagements?\s+(recus|donnes)|remuneration|effectif\s+des"
)


@dataclass(frozen=True)
class UnitCall:
    unit: str
    evidence: str
    page: int | None

    def __str__(self) -> str:
        where = f"p{self.page}" if self.page else "default"
        return f"{self.unit} ({where}: {self.evidence})"


def _claims(text: str, page: int) -> list[tuple[str, str, bool]]:
    """(unit, quoted evidence, is_scoped) for every unit claim in `text`."""
    out = []
    for pattern, unit in ((_KEUR_CLAIM, KEUR), (_EUR_CLAIM, EUR)):
        for match in pattern.finditer(text):
            window = text[max(0, match.start() - 90): match.end() + 40]
            out.append((unit, text[max(0, match.start() - 34): match.end()].strip(),
                        bool(_SCHEDULE.search(window))))
    return out


def detect(ocr_dir: str, statement_pages: list[int]) -> UnitCall:
    """The unit governing `statement_pages`, with the evidence for it."""
    on_page: list[tuple[str, str, int]] = []
    general: list[tuple[str, str, int]] = []

    for path in sorted(glob.glob(os.path.join(ocr_dir, "page_*.json"))):
        with open(path, encoding="utf-8") as fh:
            page_json = json.load(fh)
        page = page_json["page"]
        text = normalise(" ".join(line["text"] for line in page_json["ocr"]))
        for unit, evidence, scoped in _claims(text, page):
            if scoped:
                continue          # governs one annexe schedule, not the liasse
            if page in statement_pages:
                on_page.append((unit, evidence, page))
            else:
                general.append((unit, evidence, page))

    # A statement printed on the page we read beats one printed elsewhere.
    for pool in (on_page, general):
        thousands = [c for c in pool if c[0] == KEUR]
        if thousands:
            return UnitCall(KEUR, thousands[0][1], thousands[0][2])
        if pool:
            return UnitCall(EUR, pool[0][1], pool[0][2])

    return UnitCall(EUR, "no declaration; CERFA forms are filed in euros", None)
