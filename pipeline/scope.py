"""The fifteen filings this challenge puts in scope, from challenges/bilan/BRIEF.md."""

SCOPE = [
    ("820561470", "bilan_2023-06-05_6493e4372f502414800f8164"),
    ("820561470", "bilan_2023-06-13_6543d3fd08093cdace058668"),
    ("820561470", "bilan_2024-01-15_67458f18cea78a70070fa226"),
    ("328024377", "bilan_2020-12-24_63e8ebbb54febda17c19ee7c"),
    ("328024377", "bilan_2021-12-17_63e8ebbb54febda17c19ee7d"),
    ("328024377", "bilan_2022-12-13_63e8ebbb54febda17c19ee7e"),
    ("445070311", "bilan_2022-02-14_63e2481c916269756a09542b"),
    ("445070311", "bilan_2023-11-21_65a4095d5fd178b16b09b860"),
    ("445070311", "bilan_2025-05-15_6860f28ca0138eae340c7453"),
    ("504304205", "bilan_2017-05-31_63e13943526e1f30cd100db5"),
    ("504304205", "bilan_2018-10-24_63e13943526e1f30cd100db6"),
    ("504304205", "bilan_2024-08-06_66cd893cedec9b09d50191e8"),
    ("401009741", "bilan_2022-11-30_63e881158be6eb9f9d1ff975"),
    ("401009741", "bilan_2023-11-20_65784e5da67d84faf4042736"),
    ("401009741", "bilan_2025-10-03_68f0a715f28d8aaf48046416"),
]


def paths(siren: str, stem: str) -> dict[str, str]:
    doc_id = stem.rsplit("_", 1)[1]
    return {
        "pdf": f"data/{siren}/bilans/pdf/{stem}.pdf",
        "ocr": f"data/{siren}/bilans/ocr/{doc_id}",
        "meta": f"data/{siren}/bilans/meta/{stem}.json",
        "doc_id": doc_id,
    }
