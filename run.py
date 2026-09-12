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
import sys
import time
from dataclasses import dataclass

from pipeline import checks, units
from pipeline.fields import Field, Reading, calibration, read
from pipeline.geometry import normalise_box
from pipeline.labels import (CASH, MARKETABLE_SECURITIES, SHARE_CAPITAL,
                             TOTAL_ASSETS, TOTAL_EQUITY, TOTAL_LIABILITIES,
                             best_row)
from pipeline.numbers import figures_in
from pipeline.ocr_rows import load_page, rows_of
from pipeline.pages import ACTIF, PASSIF, classify_document
from pipeline.scope import SCOPE, paths

# The fields wired up so far. The seven P&L fields are not among them yet, and
# the README says so: an absent field should not read as a clean sheet.
BALANCE_SHEET = [
    (Field("BS_TOTAL_ASSETS_FRGAAP", "CN", TOTAL_ASSETS), ACTIF),
    (Field("BS_TOTAL_EQUITY_FRGAAP", "DL", TOTAL_EQUITY), PASSIF),
    (Field("BS_CAPITAL_EQUITY_FRGAAP", "DA", SHARE_CAPITAL), PASSIF),
]

# Cash is built rather than printed: disponibilites plus marketable securities.
CASH_PARTS = [
    Field("_cash", "CG", CASH),
    Field("_securities", "CD", MARKETABLE_SECURITIES),
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

    column = {
        ACTIF: calibration(actif_rows, anchor) if anchor else None,
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

    if meta.get("confidentiality") == "Partiellement confidentiel":
        notes.append("income statement withheld from publication (L. 232-25): "
                     "the seven P&L fields are absent from this filing")

    return DocumentResult(entry, notes)


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
