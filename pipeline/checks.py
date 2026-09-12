"""Checks that can fail without an answer key, used to gate what we report.

The challenge publishes no answer key and says the answer is often contested,
so the only honest confidence is the one these identities buy:

*   total assets equals total liabilities, which French law requires -- but
    only counts as evidence when the two are printed on different pages. A
    sideways filing prints actif and passif on one sheet, where matching a
    figure against itself proves nothing;
*   gross minus depreciation equals net, along any row of the bilan actif;
*   each company files three consecutive years, so this year's figure should
    reappear as next year's comparative.

They are cheap, they need no external source, and they catch the one failure
this challenge punishes hardest: a plausible number that is quietly wrong.
445070311's 2025 filing reads total assets as 952 242 where the page says
10 952 242 -- the OCR dropped a leading digit -- and gross-minus-depreciation
is what notices.
"""

from __future__ import annotations

TOLERANCE = 2.0          # OCR rounds; two euros of slack on an identity


def reconciles(assets: float | None, liabilities: float | None,
               independent: bool) -> bool | None:
    """True/False when the identity can be tested, None when it cannot."""
    if assets is None or liabilities is None or not independent:
        return None
    return abs(assets - liabilities) <= TOLERANCE


def gross_less_depreciation(figures: list[float]) -> bool | None:
    """Check gross - depreciation = net on a bilan actif row.

    Only meaningful with at least three figures: gross, depreciation, net.
    """
    if len(figures) < 3:
        return None
    gross, depreciation, net = figures[0], figures[1], figures[2]
    return abs(gross - depreciation - net) <= TOLERANCE


def chains(current: float | None, previous_filing_comparative: float | None) -> bool | None:
    """This year's figure against the next filing's N-1 column."""
    if current is None or previous_filing_comparative is None:
        return None
    return abs(current - previous_filing_comparative) <= TOLERANCE


# Relations that hold in any real balance sheet. They do not prove a figure
# right, but each one catches a class of silent error that the schema, the
# reconciliation and the eye all miss -- every one of these fired on a real
# defect while this was being built.
_COHERENCE = (
    ("BS_TOTAL_EQUITY_FRGAAP", "BS_TOTAL_ASSETS_FRGAAP", "equity exceeds total assets"),
    ("BS_CAPITAL_EQUITY_FRGAAP", "BS_TOTAL_ASSETS_FRGAAP", "share capital exceeds total assets"),
    ("BS_CASH_CURRENT_ASSET_FRGAAP", "BS_TOTAL_ASSETS_FRGAAP", "cash exceeds total assets"),
    ("PL_PERSONNEL_COSTS_FRGAAP", "PL_REVENUE_FRGAAP", "personnel cost exceeds revenue"),
    ("PL_INCOME_TAX_FRGAAP", "PL_REVENUE_FRGAAP", "income tax exceeds revenue"),
)


def coherence(fields: list[dict]) -> list[str]:
    """Complaints about a filing's extracted fields, as plain sentences.

    A wrong figure usually looks fine on its own; it is next to its siblings
    that it stops making sense. Reading total assets off a stray line code
    gave 6 987 for a company whose equity read 1 010 320 -- valid JSON, a box
    on a real number, and impossible.
    """
    values = {f["field_key"]: f["value"] for f in fields}
    out = []
    for smaller, larger, complaint in _COHERENCE:
        a, b = values.get(smaller), values.get(larger)
        if a is not None and b is not None and abs(a) > abs(b):
            out.append(f"{complaint}: {a:,.0f} vs {b:,.0f}".replace(",", " "))
    return out
