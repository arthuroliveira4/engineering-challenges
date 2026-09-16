# Bilan challenge — reading French annual accounts

Extracts twelve financial fields from the fifteen filings in scope, each with
the page and box it was read from, using the OCR shipped in `data/` and no
model at all.

**Recording (~3 min):** https://www.loom.com/share/ad5621c438684c98b18e7a316c1caeae

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
subtotal one row up, is obvious on sight and invisible in a schema check.

It earned its place. Reading all fifteen sheets found nine defects that the
schema, the identities and I had all passed over — six wrong figures, four
misplaced boxes and two figures dropped from pages that state them plainly.
They are listed under *Accuracy* below, each with its cause. If you read one
thing in this repository after `results.json`, read that table.

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
| Time | **0.002–0.006 s per page**, one core — 1 to 2.5 s for all 415 pages |
| Coverage | **121 of a possible 145 values** across 15 filings |

The 145 is not 12 × 15. Five filings withhold their income statement from
publication by law, so 35 of the 180 nominal values do not exist to be read —
see below.

The time is a range and not a figure because that is what five consecutive
runs of the same code on the same corpus gave: 0.0024, 0.0032, 0.0031, 0.0058
and 0.0060 seconds per page. The work is reading 415 small JSON files off a
laptop disk, so the spread is the filesystem and whatever else the machine was
doing, not the pipeline. `results.json` carries the figure from the run that
wrote it, which is why it will not match this line exactly; quoting one of
those runs to two significant figures and calling it *the* number would be
tidier and less true.

**What it bought.** Everything, at zero marginal cost, is the wrong way to
read that. What the choice really bought is *auditability*: every figure
traces to a box on a page, and when a value is wrong I can see which rule
produced it. A vision model would have covered more of the awkward layouts and
told me less about why.

**What it cost.** 24 values. Fewer than that are anyone's to win: 18 of them
are figures the documents do not publish, and no amount of reading recovers
what was never filed. Six are ones I would rather have had — see *What I cut*
for each, by name.

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
| vision only where the rules failed | 8 | **€0.09** | €0.22 | €0.04 |
| rules only (this submission) | 0 | €0.00 | €0.00 | €0.00 |

Those 8 are every gap sitting on a page the pipeline located, which is what a
fallback queue would actually contain. At most 6 of them are values to win —
two are cells this filing prints empty, where the model confirms an absence
rather than recovering a figure. Worth knowing, not worth counting as
coverage.

Sending everything to a model costs 52× what sending the failures costs. The
rules are what make that targeting possible: they do not merely extract, they
say *which page they failed on*.
Amortised over the corpus the targeted fallback is €0.0002 per page — two
hundredths of a cent.

So the honest reading of the trade-off is not "rules are free, models cost
money". It is that **a rules-first pipeline turns a €4.55 problem into a €0.09
problem**, and the €0.09 is worth spending.

**What I could not measure.** How many of those 6 values a vision model would
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

The `confidence` field records which route produced a value:

| | route |
|---|---|
| 0.98 | total assets, reconciled against total liabilities on a separate page |
| 0.95 | read from a CERFA line code |
| 0.90 | built by summing printed lines |
| 0.80 | matched by wording, with a calibrated column |
| 0.75 | a sum whose parts were matched by wording, or a headcount read from prose |
| 0.55 | matched by wording alone, with no column to check it against |

Median is 0.90.

**One box is coarser than the rest, and it is the headcount.** Three filings
state it in a sentence of the annexe rather than against line YP, and the OCR
returns that whole sentence as a single box:

```json
{ "value": 47, "snippet": "Effectif moyen du personnel : 47 personnes dont 9 apprentis et 2 handicapés." }
```

So the box spans the sentence, not the digits — and that sentence prints three
numbers. There is no finer box to report: those pages carry no text layer, and
the OCR does not split the line, so a tighter box would have to be interpolated
from character positions rather than read. That is the same line I refused to
cross on 445070311's total assets, so I did not cross it here either. The
`snippet` names the wording the figure was taken from, which is what makes the
claim checkable; where the liasse prints YP properly — 504304205, 2017 — the
box is on the digit alone and the confidence is 0.95.

**Then I read all fifteen sheets.** Identities and the schema between them
missed nine defects, because both are blind to the same thing: a figure that
is well-formed, in range, and simply the wrong figure. Every one of these was
found by looking at the box on the page.

| what the sheet showed | what it was |
|---|---|
| cost of goods sold short by one line on three filings | the accountant's software writes *"Variation de stock **de** marchandises"* where the liasse writes *"(marchandises)"* |
| income tax equal to operating profit | on a sideways sheet the wording sat at the *end* of a rebuilt row, so the first figure on it belonged to the account printed to the left |
| personnel cost missing wages | OCR read *"Salaires et trait**ern**ents"* |
| cash 68 856 too high | the box was on the gross column; with total assets withheld there was no anchor to calibrate against |
| cost of goods sold mixing 2017 and 2016 | FV's own cell is empty that year, so "the nearest figure to the right of the code" reached into the prior-year column |
| an income tax that was last year's | same cause, same company, one year later — HK empty |
| two empty crops and two boxes in blank cells | every page of that filing carries /Rotate 270, and the boxes were normalised against the mediabox rather than the page as rendered |
| depreciation absent though plainly printed | *"exceptionnelle"*, which disqualifies that label, was printed in the **other half** of a sideways sheet |
| total equity absent on three filings | the section heading *"SITUATION NETTE"* outranked *"TOTAL situation nette :"*, which is the line with the figure on it |

Six were figures reported wrongly, one was four boxes pointing at the wrong
part of the page, and two were figures the page states plainly that the
pipeline dropped. None would have surfaced any other way. That is the
argument for `verify.py` being in this repository rather than in my scratch
directory — and for reading the output rather than the summary of it, which
is the habit I would take from this challenge.

## Five things the brief does not mention

These came out of the data and are worth reporting whether or not they were
intended.

**1. Seven of the fifteen filings are not the liasse fiscale.** They are
balance sheets laid out by the accountant's own software — same French
wording, no CERFA form number, no line codes. Three signals agree on which,
and they agree exactly: the seven print no `DGFiP`, carry no form number, and
yield zero CERFA codes on the page their balance sheet sits on, while the
other eight yield between ten and fifteen.

| | filings |
|---|---|
| official liasse | `328024377` 2021 · 2022, `504304205` ×3, `401009741` ×3 |
| accountant's software | `820561470` ×3, `328024377` 2020, `445070311` ×3 |

Anchoring on form numbers or page positions works on eight and fails silently
on seven, so the pipeline reads by line code where one exists and by wording
where none does. Note that `328024377` files both ways across three years —
whichever layout a filing uses is a property of the filing, never of the
company.

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

**5. Sideways text and a rotated page are two different problems, and one
filing has the second.** Every page of `401009741`'s 2025 filing carries
`/Rotate 270`: its mediabox is 841 × 595 while the page as rendered — and as
the OCR measured it — is 595 × 841. Normalise a box against the mediabox and
you divide x by the height and y by the width, which is silent, survives the
schema, and puts every box on that filing somewhere else on the page.
`tools/bbox_viewer.py` reads `page.rect`, so anyone following it is fine;
anyone who reaches for `mediabox` because it sounds like the page is not.
This is worth flagging because it is invisible in every check that does not
render the result.

Also worth knowing: `fiscal_year_end` does not need to be parsed out of the
scan. The registry ships `dateCloture` in `data/<siren>/bilans/meta/`, and all
fifteen are populated from it.

## What I cut, and why

**24 of 145 values**, and every one of them has a cause I can name. Three
quarters are not failures at all — they are figures the filing does not
publish:

| # | field(s) | filings | why |
|---|---|---|---|
| 7 | average workforce | 820561470 ×3, 401009741 ×3, 445070311/2025 | the word *effectif* appears nowhere in the document |
| 1 | average workforce | 504304205/2018 | line YP is printed and its cell is empty |
| 1 | average workforce | 504304205/2024 | line YP is printed as 0, and the schema says omit rather than report zero |
| 1 | income tax | 504304205/2018 | line HK is printed and its cell is empty |
| 1 | total assets | 445070311/2025 | the OCR dropped a leading digit; the check catches it and I will not report a figure whose box excludes digits I inferred |
| 7 | the P&L fields | 328024377/2020 | see below |

That leaves 6 I would rather have had:

- **Share capital and cash on 328024377's 2020 filing.** Printed on a balance
  sheet we located, and simply not read. That filing loses nine values in all,
  but the other seven are its P&L, and they are counted above as absent for a
  reason worth stating: it publishes **no statutory compte de résultat** — only
  a management P&L from the accountant's report, with percent and variance
  columns. The figures it does print are not the ones asked for: *Amortissements et
  provisions* is one line where the liasse rules two (GA and GB), and its
  revenue total includes operating subsidies, which *chiffres d'affaires nets*
  does not. Reading definitions off a management report and filing them under
  FRGAAP field keys is the sort of plausible-and-wrong the brief punishes
  hardest.
- **`PL_FINANCIAL_RESULTS` on 445070311's 2022 and 2023 filings.** The wording
  is not on the page the classifier picked. The same field on the same
  company's 2025 filing now reads correctly, so this is a page-selection gap
  rather than a reading one.
- **Average workforce on 445070311's 2022 and 2023 filings.** Both state it in
  the director's report as *"l'effectif salarié moyen à la clôture de
  l'exercice s'élève à 33"* — a phrase that is either an average or a closing
  headcount depending on how you read it, from a document that is not the
  annexe. I would rather omit an ambiguous figure than file it under a field
  named *average*. This is the omission I am least sure about, and the cheapest
  for you to overturn: two numbers, both stated in plain French.
- **No vision-model fallback.** It is the obvious next move and I ran out of
  budget before it, not before deciding against it.
- **No test suite.** The `checks.py` identities do the work a test suite would,
  but they run inside the pipeline rather than beside it.

## How I used AI

I used Claude Code throughout the project, and it wrote essentially all of the
Python in this repository — every module in `pipeline/`, plus `run.py` and
`verify.py`. I am not going to dress that up: my contribution was direction,
judgement and criticising the AI's decisions, not authorship of the code.

**What I decided.** To take the bilan challenge, to read the shipped OCR with
rules rather than send pages to a vision model, and, where
`financial_fields.json` contradicts itself, to follow `notes` over `label_fr`.
That last one moves three fields and is argued in `DECISIONS.md`. I also asked
for an explanation of anything I could not follow, and did not let a step past
me until I could say why it was there.

**What I checked.** I asked for a way to see the boxes rather than be told they
were fine, which is where `verify.py` comes from, that, and trying to
understand every step and what it implied for the rest of the pipeline. It
mattered more than anything else I did, so reading all fifteen sheets turned up
nine defects in output that had already passed the schema and the
reconciliation identities. Six figures that were simply wrong, one filing whose
four boxes pointed at the wrong part of the page, and two figures dropped from
pages that state them plainly. Every one was a plausible number produced by
code that looked correct. They are listed with their causes under Accuracy.

**Where it led me wrong.** It reported the reconciliation as passing on 11 of
15 filings when several of those "matches" were coincidences between number
fragments. It wrote a check that threw away a correct figure by assuming any
three-figure row meant gross/depreciation/net. And it left a sentence in
`results.json` announcing that seven of the twelve fields were not implemented
while the same file carried their values, a plain contradiction in the one
field a reader consults to decide whether to trust the numbers, and it survived
a whole working session before anyone re-read it.
