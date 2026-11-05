import json

import pytest

from resource_platform.answer import EVENT_TYPES, Answerer, AnswerLog, find_counties, parse


@pytest.fixture
def ask(catalog, tmp_path):
    a = Answerer(catalog, AnswerLog(tmp_path / "answers.jsonl"))
    return a.ask


def test_single_figure_is_cited(ask, catalog):
    ans = ask("How much rain fell in Hale County in 2020?")
    assert ans.status == "answered" and len(ans.statements) == 1
    s = ans.statements[0]
    assert s.county == "Hale" and s.metric == "precipitation" and s.unit == "inches"
    assert catalog.resolve(s.citation)["row"]["County"] == "Hale County"
    assert ans.synthetic


def test_event_types_are_never_summed(ask):
    ans = ask("storms in Potter County in 2021")
    assert [s.metric for s in ans.statements] == EVENT_TYPES
    assert any("doesn't add" in n for n in ans.notes)


def test_daily_high_is_not_the_average(catalog):
    assert parse("average daily high temperature in Lubbock 2020", catalog).metrics == [
        "max_temp"]
    assert parse("temperature in Lubbock 2020", catalog).metrics == ["avg_temp"]
    assert parse("storm damage in Harris 2017", catalog).metrics == ["property_damage"]


def test_ranges_and_several_counties(ask):
    ans = ask("Average daily high in El Paso and Lubbock from 2020 to 2022")
    assert {(s.county, s.year) for s in ans.statements} == {
        (c, y) for c in ("El Paso", "Lubbock") for y in (2020, 2021, 2022)}


def test_partial_when_some_figures_are_missing(ask, catalog):
    row = catalog.db.execute("SELECT county, year FROM facts WHERE metric = 'precipitation' "
                             "AND value IS NULL LIMIT 1").fetchone()
    ans = ask(f"temperature and rainfall in {row[0]} County in {row[1]}")
    assert ans.status == "partial"
    assert any("Precipitation" in m and "left blank" in m for m in ans.missing)


def test_unknown_when_the_sources_have_nothing(ask):
    ans = ask("rainfall in Bexar County in 2001")
    assert ans.status == "unknown" and not ans.statements and ans.missing


def test_damage_carries_its_caveat(ask):
    ans = ask("storm damage in Harris County in 2017")
    assert any("estimates" in n for n in ans.notes)


@pytest.mark.parametrize("question,kind", [
    ("Why was 2022 so dry in Hale County?", "cause"),
    ("Will it rain in Travis County tomorrow?", "forecast"),
    ("How hot will Travis County be next year?", "forecast"),
    ("Rainfall in Travis County in 2031", "forecast"),
    ("Should Bexar County farmers plant early?", "advice"),
    ("rainfall in Springfield County in 2020", "place"),
    ("Tell me about Bexar County in 2020", "measure"),
])
def test_out_of_scope_is_declined_with_a_reason(ask, question, kind):
    ans = ask(question)
    assert ans.status == "declined" and ans.reason.startswith(kind)


def test_ambiguous_county_names(catalog):
    names = lambda t: [c.name for c in find_counties(t, catalog)]  # noqa: E731
    assert names("real rainfall for Bexar") == ["Bexar"]          # 'real' is a word here
    assert names("rainfall in Real County") == ["Real"]
    assert names("Brazos River floods near Waco in McLennan") == ["McLennan"]
    assert names("El Paso and Hudspeth") == ["El Paso", "Hudspeth"]


def test_log_is_hash_chained_and_tamper_evident(catalog, tmp_path):
    log = AnswerLog(tmp_path / "log.jsonl")
    a = Answerer(catalog, log)
    a.ask("rainfall in Hale County 2020")
    a.ask("Why is Hale dry?")
    a.ask("rainfall in Springfield County in 2020")
    assert log.verify() is None and len(log.entries()) == 3
    assert dict(log.gaps()) == {"cause": 1, "place": 1}

    lines = log.path.read_text().splitlines()
    first = json.loads(lines[0])
    first["citations"] = []
    lines[0] = json.dumps(first, sort_keys=True)
    log.path.write_text("\n".join(lines) + "\n")
    assert log.verify() == 1
