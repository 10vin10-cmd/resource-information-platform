import json

import pytest

from resource_platform.answer import USE_CATEGORIES, Answerer, AnswerLog, find_counties, parse


@pytest.fixture
def ask(catalog, tmp_path):
    a = Answerer(catalog, AnswerLog(tmp_path / "answers.jsonl"))
    return a.ask


def test_single_figure_is_cited(ask, catalog):
    ans = ask("What was irrigation use in Hale County in 2020?")
    assert ans.status == "answered" and len(ans.statements) == 1
    s = ans.statements[0]
    assert s.county == "Hale" and s.year == 2020 and s.unit == "acre-feet"
    assert catalog.resolve(s.citation)["row"]["County"] == "HALE"
    assert ans.synthetic


def test_water_use_is_never_summed(ask):
    ans = ask("How much water did Bexar County use in 2022?")
    assert [s.metric for s in ans.statements] == USE_CATEGORIES
    assert any("doesn't add" in n for n in ans.notes)


def test_ranges_and_several_counties(ask):
    ans = ask("irrigation in Lubbock and Hale from 2019 to 2021")
    assert {(s.county, s.year) for s in ans.statements} == {
        (c, y) for c in ("Lubbock", "Hale") for y in (2019, 2020, 2021)}


def test_partial_when_some_figures_are_missing(ask, catalog):
    row = catalog.db.execute("SELECT county, year FROM facts WHERE metric = 'mining' "
                             "AND value IS NULL LIMIT 1").fetchone()
    ans = ask(f"water use in {row[0]} County in {row[1]}")
    assert ans.status == "partial"
    assert any("Mining use" in m and "left blank" in m for m in ans.missing)


def test_unknown_when_the_sources_have_nothing(ask):
    ans = ask("water use in Bexar County in 2001")
    assert ans.status == "unknown" and not ans.statements and ans.missing


@pytest.mark.parametrize("question,kind", [
    ("Why did irrigation fall in Hale County?", "cause"),
    ("What will Travis County use next year?", "forecast"),
    ("What will Travis County use in 2030?", "forecast"),
    ("Water use in Travis County in 2031", "forecast"),
    ("Should Bexar County pump more groundwater?", "advice"),
    ("water use in Springfield County in 2020", "place"),
    ("Tell me about Bexar County in 2020", "measure"),
])
def test_out_of_scope_is_declined_with_a_reason(ask, question, kind):
    ans = ask(question)
    assert ans.status == "declined" and ans.reason.startswith(kind)


def test_ambiguous_county_names(catalog):
    names = lambda t: [c.name for c in find_counties(t, catalog)]  # noqa: E731
    assert names("real figures for Bexar") == ["Bexar"]           # 'real' is a word here
    assert names("water use in Real County") == ["Real"]
    assert names("Edwards Aquifer levels in Bexar") == ["Bexar"]  # aquifer, not county
    assert names("El Paso and Hudspeth") == ["El Paso", "Hudspeth"]


def test_groundwater_level_warns_when_few_wells(catalog, ask):
    row = catalog.db.execute("SELECT county, year FROM facts WHERE metric = 'wells_measured' "
                             "AND value < 5 LIMIT 1").fetchone()
    ans = ask(f"depth to groundwater in {row[0]} County in {row[1]}")
    assert ans.status == "answered" and any("unreliable" in n for n in ans.notes)
    assert parse("water table in Lubbock 2020", catalog).metrics == ["depth_to_water"]


def test_log_is_hash_chained_and_tamper_evident(catalog, tmp_path):
    log = AnswerLog(tmp_path / "log.jsonl")
    a = Answerer(catalog, log)
    a.ask("irrigation in Hale County 2020")
    a.ask("Why is Hale dry?")
    a.ask("water use in Springfield County in 2020")
    assert log.verify() is None and len(log.entries()) == 3
    assert dict(log.gaps()) == {"cause": 1, "place": 1}

    lines = log.path.read_text().splitlines()
    first = json.loads(lines[0])
    first["citations"] = []
    lines[0] = json.dumps(first, sort_keys=True)
    log.path.write_text("\n".join(lines) + "\n")
    assert log.verify() == 1
