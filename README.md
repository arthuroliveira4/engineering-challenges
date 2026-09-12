# Bilan challenge — reading French annual accounts

Extracts twelve financial fields from the fifteen filings in scope, each with
the page and box it was read from, using the OCR shipped in `data/` and no
model at all.

**Recording (~3 min):** TODO — paste the Loom link here before opening the PR.

The original challenge brief is at
[`challenges/bilan/BRIEF.md`](challenges/bilan/BRIEF.md); this README replaces
the repository's own, which described the challenge rather than the answer.

---

## How to run it

```bash
pip install pymupdf pillow
python run.py                # writes results.json at the repository root
python run.py --report       # and prints coverage and caveats to stderr
python verify.py             # renders every value back onto its page, into verify/
```

`verify.py` is how I checked this, and the fastest way for you to: it crops the
row each figure was read from, draws the submitted box on it, and captions it
with the field and the value claimed. A box on the prior-year column, or on a
subtotal one row up, is obvious on sight and invisible in a schema check. It
earned its place — reading those sheets is what caught cost of goods sold
silently dropping a line on three filings, because the accountant's software
writes *"Variation de stock **de** marchandises"* where the liasse writes
*"Variation de stock (marchandises)"*.

No API key and no network. `.env.example` is empty on purpose and says why.

```
pipeline/
  ocr_rows.py   rebuild a page into reading-order rows
  pages.py      decide which statement each page carries
  numbers.py    read French figures, repair what the OCR broke
  labels.py     the French wording of each field, and its decoys
  liasse.py     read a field by its CERFA line code
  columns.py    decide which column holds the current exercise
  fields.py     one field, by whichever route the filing supports
  units.py      EUR or kEUR, from evidence that governs the page
  checks.py     identities that can fail without an answer key
  geometry.py   300-dpi pixels to the 0-1 boxes the schema wants
run.py          orchestrates the above, writes results.json
DECISIONS.md    the judgement calls, and what would overturn each
```

## The trade-off

**What I chose.** The shipped OCR plus rules. No vision model, no OCR engine
of my own, no API.

| | measured |
|---|---|
| Cost | **€0.00 per page** — nothing is called |
| Time | **0.0020 s per page**, 0.84 s for all 415 pages, one core |
| Coverage | **116 of a possible 145 values** across 15 filings |

The 145 is not 12 × 15. Five filings withhold their income statement from
publication by law, so 35 of the 180 nominal values do not exist to be read —
see below.

**What it bought.** Everything, at zero marginal cost, is the wrong way to
read that. What the choice really bought is *auditability*: every figure
traces to a box on a page, and when a value is wrong I can see which rule
produced it. A vision model would have covered more of the awkward layouts and
told me less about why.

**What it cost.** Roughly 29 values that a vision model would probably have
picked up: pages where the wording runs into a neighbouring row, an annexe
schedule that our page classifier does not recognise, one figure the OCR
mangled beyond safe repair.

**What the alternative would have cost.** Zero is only half a trade-off, so
here is the other side, derived rather than guessed — token counts against
published prices, which the schema names as an acceptable derivation.

An A4 page renders to 1098 × 1568 px after the API's downscale, which is 2 296
image tokens; a prompt carrying the twelve French labels and the output schema
is about 700 more; the response is 590 tokens, measured from the size of a
complete document entry in this file's own output. At Claude Sonnet 5 rates
($2.00 / $10.00 per MTok) that is **€0.011 per page**.

What matters is not the per-page rate but how many pages you send:

| | pages sent | Sonnet 5 | Opus 5 | Haiku 4.5 |
|---|---|---|---|---|
| vision over the whole corpus | 415 | €4.55 | €11.37 | €2.27 |
| vision only where the rules failed | 11 | **€0.12** | €0.30 | €0.06 |
| rules only (this submission) | 0 | €0.00 | €0.00 | €0.00 |

Sending everything to a model costs 38× what sending the failures costs, for
the same 13 recoverable values. The rules are what make the targeting
possible: they do not merely extract, they say *which page they failed on*.
Amortised over the corpus the targeted fallback is €0.0003 per page — three
hundredths of a cent.

So the honest reading of the trade-off is not "rules are free, models cost
money". It is that **a rules-first pipeline turns a €4.55 problem into a €0.12
problem**, and the €0.12 is worth spending.

**What I could not measure.** How many of those 13 values a vision model would
actually recover. That needs a real run against a real key, and I did not have
one. The cost side above is derived from published prices and real token
counts; the accuracy side is not, and I am not going to invent a number for
the half I could not test. That is the biggest gap in this submission.

**What I would do with a week.** Build that fallback and measure it, which
closes the gap above. The plumbing is already there: `run.py` records which
page each missing field was expected on, so the fallback has its work queue
without any new analysis. I would also promote the `checks.py` identities from
a gate inside the run to a test suite beside it, so a regression surfaces as a
failing test rather than as a quietly absent field.

## Accuracy, without an answer key

The brief says there is no answer key and the answer is often contested, so I
did not invent a confidence number. Every figure is instead put through
identities the filings themselves must satisfy:

| check | what it proves | result |
|---|---|---|
| total assets = total liabilities | required by French law | **15 / 15** |
| gross − depreciation = net | internal to the bilan actif | used as the gate where the reconciliation is circular |
| France + export = net revenue | internal to the compte de résultat | used to pick the revenue column |
| this year's figure = next filing's N-1 | three consecutive filings per company | confirmed on 820561470: 638 962 → 638 554 → 866 478 |

Which check applies depends on the layout. Where actif and passif are printed
on separate pages the reconciliation is independent evidence and stands alone.
Where they share a sheet — as the sideways filings do — comparing a figure
against itself proves nothing, so gross-less-depreciation decides instead.

That second case is not hypothetical. `445070311`'s 2025 filing reads total
assets as `952 242` where the page says `10 952 242`; the OCR dropped a
leading digit. The check catches it and the field is omitted. I can reconstruct
the true value two ways, but arithmetic is not reading, and the box I would
report would not span the digits I used.

The `confidence` field records which route produced a value: 0.95 read from a
CERFA line code, 0.90 built by summing printed lines, 0.80 matched by wording
with a calibrated column, 0.55 matched by wording alone. Median is 0.90.

## Four things the brief does not mention

These came out of the data and are worth reporting whether or not they were
intended.

**1. Six of the fifteen filings are not the liasse fiscale.** They are balance
sheets laid out by the accountant's own software — same French wording, no
CERFA form number, no line codes. Anchoring on form numbers or page positions
works on nine filings and fails silently on six, so the pipeline reads by line
code where one exists and by wording where none does.

**2. Sideways pages are in three companies, not one.** The brief flags
`820561470`. In the pages shipped, `445070311` has 9 rotated pages,
`504304205` has 4, and `820561470` has 1. Rotation is detected per page from
the shape of the text boxes, never from the company.

**3. `328024377` files in euros, not thousands.** The brief flags it as
reporting in thousands. Its accounting policy note reads *"sauf mention, les
montants sont exprimés en euros"*; the `K€` statement sits inside the tableau
des filiales et participations and governs that schedule. Magnitude agrees
with the note — total assets 5 641 580 and revenue 4 982 166 for a Lyon
chocolatier are millions, not billions. All fifteen filings resolve to EUR.
This is the finding I am least certain of, and `DECISIONS.md` says what would
overturn it.

**4. Thirty-five values are absent by law, not by failure.** Five filings
carry no compte de résultat. The registry metadata marks exactly those five
`"confidentiality": "Partiellement confidentiel"`, and the correlation is 5 of
5. Under article L. 232-25 of the Code de commerce a small company may declare
its income statement not be made public. Those fields are omitted, per the
schema's own rule.

Also worth knowing: `fiscal_year_end` does not need to be parsed out of the
scan. The registry ships `dateCloture` in `data/<siren>/bilans/meta/`, and all
fifteen are populated from it.

## What I cut, and why

- **29 of 145 values.** The gaps by field: financial result 6/10, average
  workforce 3/15, total equity 12/15, and one total assets deliberately
  omitted. Each has a named cause, not a shrug.
- **No vision-model fallback.** It is the obvious next move and I ran out of
  budget before it, not before deciding against it.
- **`PL_FINANCIAL_RESULTS` on `445070311`.** The wording is glued to the end of
  a neighbouring row by my row reconstruction, so the figures it finds belong
  to another account. Reporting them would be exactly the failure the brief
  says it punishes hardest, so the field is left out.
- **No test suite.** The `checks.py` identities do the work a test suite would,
  but they run inside the pipeline rather than beside it.

## How I used AI

TODO — Arthur, this section must be yours and honest. Draft, to correct:

> I used Claude (Claude Code) throughout, as a pair rather than an autocomplete.
> It wrote essentially all of the Python here. What I kept for myself was the
> direction and the judgement calls: which challenge to take, which route to
> try, and the schema's contradictions — I decided `BS_CAPITAL_EQUITY` means
> share capital alone, and that decision propagated into two more fields.
>
> Where it led me wrong: it proposed a reconciliation check that reported
> 11 of 15 passing, and the number was inflated — several "matches" were
> coincidences between number fragments. It also wrote a check that discarded a
> correct figure by assuming a three-figure row meant gross/depreciation/net.
> Both were caught by looking at the printed output rather than trusting the
> summary, which is the habit I would take from this.
>
> I read every module before committing it and can defend each decision in
> `DECISIONS.md`; where I could not follow the reasoning, I asked until I could.

*(Edit the above so it matches what you actually did. An honest short paragraph
is worth more to them than a long one — their words.)*
