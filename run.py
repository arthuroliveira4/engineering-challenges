#!/usr/bin/env python3
"""Build results.json from the shipped OCR.

    python run.py              # writes results.json at the repository root
    python run.py --report     # and prints coverage and caveats to stderr

No network, no API key, no model: a page costs what it costs to read a JSON
file off disk. README.md says what that trade buys and what it gives up.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
import time
from dataclasses import dataclass

from pipeline import checks, units
from pipeline.fields import Field, Reading, calibration, read
from pipeline.columns import calibrate_by_identity
from pipeline.geometry import normalise_box
from pipeline.labels import (AVG_WORKFORCE, CASH, DEPRECIATION,
                             EXTERNAL_SERVICES, FINANCIAL_RESULT, INCOME_TAX,
                             MARKETABLE_SECURITIES, PURCHASES_GOODS,
                             PURCHASES_MATERIALS, REVENUE, SHARE_CAPITAL,
                             SOCIAL_CHARGES, STOCK_GOODS, STOCK_MATERIALS,
                             TOTAL_ASSETS, TOTAL_EQUITY, TOTAL_LIABILITIES,
                             WAGES, best_row)
from pipeline.numbers import figures_in
from pipeline.ocr_rows import load_page, rows_of
from pipeline.pages import (ACTIF, PASSIF, RESULTAT, RESULTAT_SUITE,
                            WORKFORCE, classify_document)
from pipeline.scope import SCOPE, paths

# Bilan. Total assets is read first: it anchors the current-year column for
# everything else on the two pages.
BALANCE_SHEET = [
    # No code: the liasse prints CO for the gross total and 1A for the
    # depreciation, and leaves the net column of TOTAL GENERAL unlabelled.
    # CN is "ecarts de conversion actif" and reading it here was a mistake.
    (Field("BS_TOTAL_ASSETS_FRGAAP", None, TOTAL_ASSETS), ACTIF),
    (Field("BS_TOTAL_EQUITY_FRGAAP", "DL", TOTAL_EQUITY), PASSIF),
    (Field("BS_CAPITAL_EQUITY_FRGAAP", "DA", SHARE_CAPITAL), PASSIF),
]

# Cash is built rather than printed: disponibilites plus marketable securities.
CASH_PARTS = [
    Field("_cash", "CG", CASH),
    Field("_securities", "CE", MARKETABLE_SECURITIES),   # CE is net; CD is gross
]

# Compte de resultat. Single-line fields first.
INCOME_STATEMENT = [
    (Field("PL_EXT_SERVICES_COSTS_FRGAAP", "FW", EXTERNAL_SERVICES), RESULTAT),
    (Field("PL_DEPRECIATION_AMORTIZATION_FRGAAP", "GA", DEPRECIATION), RESULTAT),
    (Field("PL_FINANCIAL_RESULTS_FRGAAP", "GV", FINANCIAL_RESULT), RESULTAT),
    (Field("PL_INCOME_TAX_FRGAAP", "HK", INCOME_TAX), RESULTAT_SUITE),
]

# Personnel cost is wages plus social charges, two printed lines.
PERSONNEL_PARTS = [
    Field("_wages", "FY", WAGES),
    Field("_social", "FZ", SOCIAL_CHARGES),
]

# Cost of goods sold is not printed at all: purchases plus the movement in
# inventory. The stock lines are signed and are added as printed.
COGS_PARTS = [
    Field("_purch_goods", "FS", PURCHASES_GOODS),
    Field("_stock_goods", "FT", STOCK_GOODS),
    Field("_purch_materials", "FU", PURCHASES_MATERIALS),
    Field("_stock_materials", "FV", STOCK_MATERIALS),
]


@dataclass
class DocumentResult:
    entry: dict
    notes: list[str]


def _meta(meta_path: str) -> dict:
    try:
        with open(meta_path, encoding="utf-8") as fh:
            return json.load(fh)
    except OSError:
        return {}


def emit(reading: Reading, key: str, unit: str, pdf: str) -> dict:
    """One entry of the fields array, box included."""
    return {
        "field_key": key,
        "value": reading.value,
        "unit": unit,
        "page": reading.page,
        "bbox": normalise_box(reading.cells, pdf, reading.page),
        "snippet": " ".join(c.text for c in reading.cells)[:120],
        "confidence": round(max(reading.confidence, 0.0), 2),
    }


def process(siren: str, stem: str) -> DocumentResult:
    p = paths(siren, stem)
    meta = _meta(p["meta"])
    notes: list[str] = []

    statements = classify_document(p["ocr"])
    actif_page = statements.get(ACTIF, [None])[0]
    passif_page = statements.get(PASSIF, [None])[0]

    entry = {
        "pdf": p["pdf"],
        "siren": siren,
        # The filename carries the deposit date, which is not what the schema
        # asks for. The registry ships the closing date beside it.
        "fiscal_year_end": meta.get("dateCloture"),
        "fields": [],
    }

    if actif_page is None or passif_page is None:
        notes.append("no balance sheet located; nothing reported")
        return DocumentResult(entry, notes)

    actif_rows = rows_of(load_page(p["ocr"], actif_page))
    passif_rows = (actif_rows if passif_page == actif_page
                   else rows_of(load_page(p["ocr"], passif_page)))

    # Calibrate the current-year column against the one figure two independent
    # readings agree on: total assets, matched against total liabilities.
    assets_row = best_row(actif_rows, TOTAL_ASSETS)
    liabilities_row = best_row(passif_rows, TOTAL_LIABILITIES)
    assets_figures = figures_in(assets_row) if assets_row else []
    liabilities_figures = figures_in(liabilities_row) if liabilities_row else []
    assets_values = [v for v, _ in assets_figures]
    anchor = next((v for v, _ in liabilities_figures if v in assets_values), None)

    # Two checks, and which one applies depends on the layout.
    #
    # Where actif and passif are printed on separate pages, the reconciliation
    # is independent evidence and French law requires it to hold, so it
    # settles the figure on its own.
    #
    # Where they share a sheet -- as the sideways filings do -- matching a
    # figure against itself proves nothing, and we fall back to gross less
    # depreciation equals net. That is the check that notices 445070311's 2025
    # filing reading 952 242 where the page says 10 952 242.
    #
    # Gross-less-depreciation is not applied to the independent case: a row
    # printing three figures is ambiguous between (gross, depreciation, net)
    # and (gross, net, prior year), and reading it the wrong way discards good
    # figures -- it threw away 820561470's 2023 total assets, which chains
    # correctly against both of its neighbouring filings.
    independent = actif_page != passif_page
    if anchor is not None and not independent:
        notes.append("actif and passif printed on one sheet: reconciliation is "
                     "not independent, falling back to gross-less-depreciation")
        if checks.gross_less_depreciation(assets_values) is not True:
            notes.append("gross-less-depreciation fails on total assets "
                         f"{[int(v) for v in assets_values[:3]]}: omitted rather "
                         "than reported")
            anchor = None

    unit = units.detect(p["ocr"], [actif_page, passif_page]).unit

    # With a proved figure we calibrate against it. Without one -- the figure
    # was withheld -- the actif can still calibrate itself: gross less
    # depreciation equals net on every line, so the rows that satisfy it agree
    # on where the net column is. Otherwise cash reads the gross column.
    column = {
        ACTIF: (calibration(actif_rows, anchor) if anchor
                else calibrate_by_identity(actif_rows)),
        PASSIF: calibration(passif_rows, anchor) if anchor else None,
    }
    rows_for = {ACTIF: actif_rows, PASSIF: passif_rows}
    page_for = {ACTIF: actif_page, PASSIF: passif_page}

    for field, statement in BALANCE_SHEET:
        if field.key == "BS_TOTAL_ASSETS_FRGAAP" and anchor is None:
            continue
        reading = read(field, rows_for[statement], page_for[statement], column[statement])
        if reading is None:
            continue
        if field.key == "BS_TOTAL_ASSETS_FRGAAP" and independent:
            reading.confidence = 0.98
        entry["fields"].append(emit(reading, field.key, unit, p["pdf"]))

    parts = [read(f, actif_rows, actif_page, column[ACTIF]) for f in CASH_PARTS]
    parts = [r for r in parts if r]
    if parts:
        built = Reading(
            sum(r.value for r in parts),
            [c for r in parts for c in r.cells],
            actif_page,
            "sum of rows",
            min(r.confidence for r in parts) - 0.05,
        )
        entry["fields"].append(emit(built, "BS_CASH_CURRENT_ASSET_FRGAAP", unit, p["pdf"]))

    entry["fields"].extend(income_statement(p, statements, unit, notes))

    notes.extend(checks.coherence(entry["fields"]))

    if meta.get("confidentiality") == "Partiellement confidentiel":
        notes.append("income statement withheld from publication (L. 232-25): "
                     "the seven P&L fields are absent from this filing")

    return DocumentResult(entry, notes)


def _sum_parts(parts_fields, rows, page, key, unit, pdf, penalty=0.05):
    """A field built by adding printed lines, or None when none of them are there.

    The box spans every line used, because that is where the value came from;
    reporting only the first would point at a figure that is not the one we
    are claiming.
    """
    parts = [read(f, rows, page, None) for f in parts_fields]
    parts = [r for r in parts if r]
    if not parts:
        return None
    built = Reading(
        sum(r.value for r in parts),
        [c for r in parts for c in r.cells],
        page,
        f"sum of {len(parts)} rows",
        min(r.confidence for r in parts) - penalty,
    )
    return emit(built, key, unit, pdf)


def revenue(rows, page: int, unit: str, pdf: str):
    """Net revenue: the total, not the domestic column beside it.

    The form splits revenue into France and export and then totals it, so the
    figure we want is the third on the row, not the first. Where the code FL
    is printed we take it; otherwise we take the first figure that the other
    two add up to, which checks the reading as it makes it.
    """
    from pipeline import liasse

    hit = liasse.find(rows, "FL")
    if hit:
        value, cells = hit
        return emit(Reading(value, cells, page, "code FL", 0.95),
                    "PL_REVENUE_FRGAAP", unit, pdf)

    row = best_row(rows, REVENUE)
    if not row:
        return None
    figures = figures_in(row)
    for i in range(len(figures) - 2):
        france, export, total = figures[i][0], figures[i + 1][0], figures[i + 2][0]
        if abs(france + export - total) <= checks.TOLERANCE:
            return emit(Reading(total, figures[i + 2][1], page,
                                "label; France + export reconciles", 0.90),
                        "PL_REVENUE_FRGAAP", unit, pdf)
    if figures:
        return emit(Reading(figures[0][0], figures[0][1], page,
                            "label only; no France/export split to check against", 0.55),
                    "PL_REVENUE_FRGAAP", unit, pdf)
    return None


def income_statement(p: dict, statements: dict, unit: str, notes: list[str]) -> list[dict]:
    """The seven P&L fields, where the filing publishes an income statement."""
    out: list[dict] = []
    page_of = {
        RESULTAT: statements.get(RESULTAT, [None])[0],
        RESULTAT_SUITE: statements.get(RESULTAT_SUITE, [None])[0],
    }
    # The second half of the form is where income tax sits; when it was not
    # identified separately, the first half is the better guess than nothing.
    if page_of[RESULTAT_SUITE] is None:
        page_of[RESULTAT_SUITE] = page_of[RESULTAT]
    if page_of[RESULTAT] is None:
        return out

    rows_of_page = {pg: rows_of(load_page(p["ocr"], pg))
                    for pg in set(page_of.values()) if pg}

    main = rows_of_page[page_of[RESULTAT]]

    got = revenue(main, page_of[RESULTAT], unit, p["pdf"])
    if got:
        out.append(got)

    for field, statement in INCOME_STATEMENT:
        page = page_of[statement]
        reading = read(field, rows_of_page[page], page, None)
        if reading:
            out.append(emit(reading, field.key, unit, p["pdf"]))

    for parts, key in ((PERSONNEL_PARTS, "PL_PERSONNEL_COSTS_FRGAAP"),
                       (COGS_PARTS, "PL_COGS_FRGAAP")):
        built = _sum_parts(parts, main, page_of[RESULTAT], key, unit, p["pdf"])
        if built:
            out.append(built)
        elif key == "PL_COGS_FRGAAP":
            notes.append("cost of goods sold: none of its component lines found")

    got = workforce(p, statements, p["pdf"])
    if got:
        out.append(got)

    return out


# "43 personnes" is not a figure by the rule the rest of the pipeline uses --
# more letters than digits, which is how a CERFA code is told from a value --
# but it is the only place some filings state their headcount.
_HEADCOUNT = re.compile(r"(?<![\d.,])(\d{1,5})(?![\d.,])")


def workforce(p: dict, statements: dict, pdf: str):
    """Average headcount: the one field of the twelve that is not money.

    The liasse prints it against code YP. Three filings state it in the prose
    of the annexe instead -- "Effectif moyen du personnel 43 personnes" -- so
    where the usual reading finds nothing we take the first bare integer on
    the row. The unit is `count`, never a currency.
    """
    page = statements.get(WORKFORCE, [None])[0]
    if page is None:
        return None
    rows = rows_of(load_page(p["ocr"], page))

    reading = read(Field("META_AVG_WORKFORCE_FRGAAP", "YP", AVG_WORKFORCE),
                   rows, page, None)
    if reading and reading.value:
        return emit(reading, "META_AVG_WORKFORCE_FRGAAP", "count", pdf)

    row = best_row(rows, AVG_WORKFORCE)
    if row is None:
        return None

    # The prose arrives as one box -- "Effectif moyen du personnel 43 personnes"
    # -- so there is no cell to single out. Take the first bare integer after
    # the wording, which is the headcount; anything later is a breakdown
    # ("dont 9 apprentis") and not the figure asked for.
    for cell in row.cells:
        tail = re.sub(r"^.*?effectif\s+moyen[^\d]*", "", cell.text,
                      flags=re.IGNORECASE | re.DOTALL)
        match = _HEADCOUNT.search(tail if tail != cell.text else cell.text)
        if not match:
            continue
        count = float(match.group(1))
        if 0 < count < 100000:
            return emit(Reading(count, [cell], page, "stated in the annexe prose", 0.75),
                        "META_AVG_WORKFORCE_FRGAAP", "count", pdf)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="coverage and caveats on stderr")
    ap.add_argument("-o", "--out", default="results.json")
    args = ap.parse_args()

    started = time.perf_counter()
    documents: list[dict] = []
    all_notes: list[str] = []
    pages = 0

    for siren, stem in SCOPE:
        result = process(siren, stem)
        documents.append(result.entry)
        pages += len(glob.glob(paths(siren, stem)["ocr"] + "/page_*.json"))
        all_notes.extend(f"{stem[6:16]} {siren}: {note}" for note in result.notes)

    elapsed = time.perf_counter() - started

    payload = {
        "documents": documents,
        "run": {
            "cost_eur_per_page": 0.0,
            "seconds_per_page": round(elapsed / pages, 4),
            "pages_processed": pages,
            "model": "provided OCR + rules",
            "notes": (
                "No model and no API. Every figure is read from the OCR shipped in "
                "data/, so the marginal cost of a page is zero; the only spend is the "
                f"time above, measured end to end over {pages} pages on one core, "
                "writing this file. Accuracy is not claimed against an answer key -- "
                "there is none -- but against identities the filings must satisfy: "
                "total assets equals total liabilities, and gross less depreciation "
                "equals net. Figures failing them are omitted rather than reported. "
                "Only the four balance-sheet fields are wired up; the seven P&L "
                "fields and average workforce are not yet implemented, and five "
                "filings withhold their income statement by law in any case. "
                "See README.md."
            ),
        },
    }

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    if args.report:
        filled = sum(len(d["fields"]) for d in documents)
        print(f"{len(documents)} documents, {filled} values, "
              f"{elapsed:.2f}s over {pages} pages "
              f"({elapsed / pages:.4f} s/page)", file=sys.stderr)
        for note in all_notes:
            print(f"  {note}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
