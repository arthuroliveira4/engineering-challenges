"""Decide which statement each page of a filing carries.

Labels like "TOTAL GENERAL" are not unique in these documents: the annexe
repeats them under every schedule it prints, so 445070311 alone offers
fifteen candidate pages. Matching a label across a whole filing returns
noise. Find the statement page first, then the label inside it.

Two families of filing show up in this corpus and both have to be handled:

*   the official liasse fiscale, where each page is a numbered CERFA form
    (2050 actif, 2051 passif, 2052/2053 compte de resultat) and carries
    two-letter line codes;
*   a balance sheet laid out by the accountant's own software, with the
    same French wording but no form number anywhere.

So the marker is the French heading, with the form number as corroboration
when it happens to be legible. A page can carry more than one statement: a
sideways page often prints actif and passif side by side on one sheet.
"""

from __future__ import annotations

import glob
import json
import os
import re
import unicodedata

ACTIF = "actif"
PASSIF = "passif"
RESULTAT = "resultat"
RESULTAT_SUITE = "resultat_suite"
WORKFORCE = "workforce"

# Ordered: the first pattern that fits wins for that statement.
_MARKERS = {
    ACTIF: r"bilan\s*-?\s*actif|actif\s+immobilise.*actif\s+circulant",
    PASSIF: r"bilan\s*-?\s*passif|capitaux\s+propres.*dettes",
    RESULTAT: r"compte\s+de\s+resultat",
    WORKFORCE: r"effectif\s+moyen|renseignements\s+divers",
}
_SUITE = re.compile(r"\(\s*suite\s*\)|resultat.{0,40}suite")
_FORM = re.compile(r"\b(205[0-3])\b|\b2058\s*-?\s*c\b")


def normalise(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace.

    The OCR is inconsistent about accents (RESULTAT / RÉSULTAT / RESULTAJ),
    so comparисons happen on the stripped form.
    """
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", text).strip().lower()


def classify_page(page_json: dict) -> set[str]:
    """Statements printed on this page. Empty set for annexe and cover pages."""
    from pipeline.ocr_rows import rows_of

    flat = normalise(" ".join(line["text"] for line in page_json["ocr"]))
    # Headings live in the first rows; the annexe repeats the wording lower down.
    head = normalise(" ".join(r.text for r in rows_of(page_json)[:12]))

    found = set()
    for statement, pattern in _MARKERS.items():
        if re.search(pattern, head) or re.search(pattern, flat[:1200]):
            found.add(statement)
    if RESULTAT in found and _SUITE.search(head):
        found.discard(RESULTAT)
        found.add(RESULTAT_SUITE)
    return found


def classify_document(ocr_dir: str) -> dict[str, list[int]]:
    """Map each statement to the pages carrying it, in page order."""
    out: dict[str, list[int]] = {}
    for path in sorted(glob.glob(os.path.join(ocr_dir, "page_*.json"))):
        with open(path, encoding="utf-8") as fh:
            page_json = json.load(fh)
        for statement in classify_page(page_json):
            out.setdefault(statement, []).append(page_json["page"])
    return out
