# Decisions

Judgement calls this pipeline makes, and the evidence behind each. The brief
says the answer to work like this is often contested and there is no answer
key, so what follows is reasoning, not assertion. Each entry names what could
make it wrong.

## Units: every filing in scope is EUR, including 328024377

The brief flags `328024377` as reporting in thousands. Its own filing
disagrees, in three ways:

- the accounting policy note reads *"sauf mention, les montants sont exprimés
  en euros"* — unless stated otherwise, amounts are in euros;
- the `K€` statement sits inside the *tableau des filiales et participations*,
  and reads *"participations étrangères, détenues entre 10 et 50%, les
  montants sont indiqués en K€"* — it governs that schedule;
- magnitude: total assets read 5 641 580 and revenue 4 982 166 for a Lyon
  chocolatier. Millions is right; billions is not.

**What would overturn this:** a `K€` marker printed on the liasse pages
themselves, which we did not find.

## BS_CAPITAL_EQUITY_FRGAAP is share capital alone

`financial_fields.json` contradicts itself on this field: `label_fr` says
*"Capital social + primes + réserves"*, while `notes` says *"Called-up share
capital (capital social)"*. The two differ by an order of magnitude — on
328024377, 152 500 against roughly 2.8 million.

We report share capital alone, read from CERFA code `DA`. The `notes` wording
is the more specific of the two, and `DA` extracts it exactly rather than by
summing lines we would then have to defend individually.

**What would overturn this:** confirmation that the production schema this was
reduced from means the broader figure.

## A figure we cannot read is omitted, not reconstructed

On `445070311/bilan_2025-05-15`, the OCR drops a leading digit from total
assets: it reads `952 242` where the page says `10 952 242`. We can prove the
correct value two ways — `12 652 618 − 1 700 376` reconciles, and it matches
the N-1 column of the previous filing — but arithmetic reconstruction is not
reading, and the box we would report would not span the digits we used.

Such fields are omitted, per the schema's own rule that a field which cannot
be established is left out rather than reported as zero.

## Five filings have no compte de résultat, and that is lawful

The seven P&L fields are absent from five of the fifteen filings. This is not
an extraction failure. The registry metadata shipped with each document says
so outright, and the correlation is exact:

| filing | `confidentiality` | P&L present |
|---|---|---|
| 820561470, all three | Partiellement confidentiel | no |
| 504304205 / 66cd893c | Partiellement confidentiel | no |
| 401009741 / 68f0a715 | Partiellement confidentiel | no |
| the other ten | Public | yes |

Under article L. 232-25 of the Code de commerce a small company may declare
that its income statement is not to be made public; the registry then
publishes the balance sheet alone. So thirty-five of the values in scope are
genuinely not in the documents, and the schema's rule applies: omit, never
report zero.

**What would overturn this:** a compte de résultat found in those filings
under wording we did not search for. We checked for six of its mandatory
lines and found at most one in each.

## Where the schema contradicts itself, we follow `notes`

`financial_fields.json` gives each field a `label_fr` and a `notes`, and three
times they disagree:

| field | `label_fr` | `notes` |
|---|---|---|
| `BS_CAPITAL_EQUITY` | capital social **+ primes + réserves** | called-up share capital |
| `PL_DEPRECIATION_AMORTIZATION` | dotations d'exploitation (amort. **+ prov.**) | depreciation and amortisation |
| `PL_COGS` | ... **+ production stockée** | built from purchases and the change in inventory |

We follow `notes` in all three: it is the more specific of the two, and one
rule applied three times is easier to defend than three separate calls. So
share capital is code `DA` alone, depreciation is `GA` alone, and cost of
goods sold is purchases plus the movement in inventory, with production
stockée excluded as a product of the period rather than a purchase.

**What would overturn this:** the production schema these were reduced from
meaning the broader reading. Swapping any of the three is a one-line change
in `pipeline/labels.py`.

## A headcount read from prose gets the sentence's box, not the digits'

Average workforce is the one field of the twelve that is not money, and the
one the filings are least consistent about. Where the liasse prints it against
line `YP` it reads like any other field and the box lands on the digits:
`504304205`'s 2017 filing reports 9 with a box 1.5% of the page wide.

Three filings of `328024377` state it in a sentence of the annexe instead, and
the OCR returns the whole sentence as one box:

```
Effectif moyen du personnel : 47 personnes dont 9 apprentis et 2 handicapés.
```

We report 47 with that sentence as its box. It is coarser than every other box
in the submission, and on this example the sentence prints three numbers, so
the box alone does not say which one is claimed.

We accept that rather than narrow it, for the same reason we omit a figure we
cannot read: a tighter box would have to be interpolated from character
positions inside the OCR polygon, and interpolation is not reading. These
pages carry no text layer to search, and the OCR does not split the line.

What makes the claim checkable instead is `snippet`, which carries the exact
wording the figure came from, and `confidence`, which is 0.75 on this route
against 0.95 for a coded read.

**What would overturn this:** a finer OCR granularity on those pages, or a text
layer to search — either would give the digits their own box, and the code
would use it without changing anything else.
