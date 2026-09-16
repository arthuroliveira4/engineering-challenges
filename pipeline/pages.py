"""Decide which statement each page of a filing carries.

Labels are not unique in these documents. "TOTAL GENERAL" is reprinted under
every schedule of the annexe -- fifteen candidate pages in 445070311 alone --
so a label hunt across a whole filing returns noise. Find the statement page
first, then the label inside it.

Heading text alone is not enough either, and gets it wrong in both directions:

    401009741 p4   "Regles et methodes comptables", which discusses the
                   compte de resultat without being one
    504304205 p22  a "COMPTES ANNUELS" cover sheet
    328024377 p4   a management P&L from the accountant's report, with percent
                   and variance columns, next to the liasse 2052 that we want

So a page is identified by its contents: a statement has to print most of the
lines that statement is required to carry. Scoring several markers rather than
trusting one heading also covers the two filing families in this corpus --
the official CERFA liasse, and the accountant-software layouts that use the
same French wording with no form number anywhere.

A page can hold more than one statement: a sideways page often prints actif
and passif side by side on a single sheet.
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

# (heading, corroborating lines, how many of them a real page must show).
_FINGERPRINTS = {
    ACTIF: (
        r"bilan\s*-?\s*actif",
        (r"immobilisations?\s+incorporelles", r"immobilisations?\s+corporelles",
         r"actif\s+circulant", r"capital\s+souscrit", r"disponibilites",
         r"creances?\s+clients", r"avances?\s+et\s+acomptes"),
        3,
    ),
    PASSIF: (
        r"bilan\s*-?\s*passif",
        (r"capitaux\s+propres", r"capital\s+social", r"reserve\s+legale",
         r"report\s+a\s+nouveau", r"dettes\s+fournisseurs", r"emprunts?\s+et\s+dettes",
         r"provisions?\s+pour\s+risques"),
        3,
    ),
    RESULTAT: (
        r"compte\s+de\s+resultat",
        (r"chiffres?\s+d.affaires\s+nets?", r"production\s+vendue",
         r"salaires\s+et\s+traitements", r"charges\s+sociales",
         r"autres\s+achats\s+et\s+charges\s+externes", r"production\s+stockee",
         r"dotations?\s+aux\s+amortissements"),
        3,
    ),
    RESULTAT_SUITE: (
        r"compte\s+de\s+resultat",
        (r"impots?\s+sur\s+les\s+benefices", r"resultat\s+exceptionnel",
         r"benefice\s+ou\s+perte", r"produits?\s+exceptionnels?",
         r"charges?\s+exceptionnelles?", r"participation\s+des\s+salaries"),
        3,
    ),
    WORKFORCE: (
        r"effectif\s+moyen|renseignements\s+divers",
        (r"effectif\s+moyen", r"personnel\s+salarie", r"apprentis",
         r"personnel\s+mis\s+a\s+disposition"),
        1,
    ),
}


def normalise(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace.

    The OCR is inconsistent about accents (RESULTAT / RESULTAT / RESULTAJ), so
    comparisons happen on the stripped form.
    """
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", text).strip().lower()


def score_page(page_json: dict) -> dict[str, int]:
    """How strongly this page matches each statement. Higher is better."""
    flat = normalise(" ".join(line["text"] for line in page_json["ocr"]))

    scores: dict[str, int] = {}
    for statement, (heading, markers, minimum) in _FINGERPRINTS.items():
        hits = sum(bool(re.search(m, flat)) for m in markers)
        if hits < minimum:
            continue
        scores[statement] = hits + (2 if re.search(heading, flat) else 0)
        # Some filings print the same statement twice: the official CERFA page
        # and the accountant's own rendering of it (504304205/66cd893c carries
        # bilan actif on p4 as form 2050 and again on p23). Prefer the form --
        # it is the one that carries the line codes we read by.
        if re.search(r"dgfip|n[o°]\s*205[0-9]|cerfa", flat):
            scores[statement] += 3

    # The two halves of the P&L share a heading and some wording; whichever
    # fingerprint fits better decides, so a page is not counted as both.
    if RESULTAT in scores and RESULTAT_SUITE in scores:
        loser = RESULTAT if scores[RESULTAT] < scores[RESULTAT_SUITE] else RESULTAT_SUITE
        del scores[loser]
    return scores


def classify_document(ocr_dir: str) -> dict[str, list[int]]:
    """Map each statement to its pages, best match first."""
    ranked: dict[str, list[tuple[int, int]]] = {}
    for path in sorted(glob.glob(os.path.join(ocr_dir, "page_*.json"))):
        with open(path, encoding="utf-8") as fh:
            page_json = json.load(fh)
        for statement, score in score_page(page_json).items():
            ranked.setdefault(statement, []).append((score, page_json["page"]))

    return {
        statement: [page for _, page in sorted(hits, key=lambda p: (-p[0], p[1]))]
        for statement, hits in ranked.items()
    }


def classify_page(page_json: dict) -> set[str]:
    """Statements printed on this page."""
    return set(score_page(page_json))
