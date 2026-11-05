from resource_platform.capture import Store
from resource_platform.catalog import Catalog, name_key, parse_number


def test_numbers_blanks_and_markers():
    assert parse_number("12,345") == (12345.0, True)
    assert parse_number("") == (None, True)        # unknown, not an error
    assert parse_number("*") == (None, True)
    assert parse_number("n.d.") == (None, False)   # an error, reported


def test_county_name_variants():
    assert name_key("De Witt") == name_key("DEWITT") == name_key("DeWitt County")


def test_sample_loads_and_statewide_row_is_an_issue(catalog):
    n = catalog.db.execute("SELECT count(*) FROM facts").fetchone()[0]
    assert n > 20_000
    issues = catalog.db.execute("SELECT problem FROM load_issues").fetchall()
    assert issues == [("unknown county 'Texas statewide'",)]
    assert catalog.db.execute("SELECT count(DISTINCT fips) FROM facts").fetchone()[0] == 254


def test_blanks_stay_unknown(catalog):
    nulls = catalog.db.execute("SELECT count(*) FROM facts WHERE value IS NULL").fetchone()[0]
    assert nulls > 0  # the sample leaves some figures blank on purpose


def test_citation_resolves_to_the_source_line(catalog):
    bexar = catalog.county_by_name("Bexar")
    fact = catalog.facts_for(bexar.fips, 2020, ["avg_temp"])[0]
    src = catalog.resolve(f"{fact['capture'][:12]}:L{fact['line']}")
    assert src["row"]["County"] == "Bexar County" and src["row"]["Year"] == "2020"
    assert float(src["row"]["Average Temperature (F)"]) == fact["value"]
    assert src["synthetic"] is True and len(src["sha256"]) == 64
    assert src["derived_from"] is None


def test_counted_figures_cite_their_raw_source(catalog):
    harris = catalog.county_by_name("Harris")
    fact = catalog.facts_for(harris.fips, 2017, ["tropical"])[0]
    src = catalog.resolve(f"{fact['capture'][:12]}:L{fact['line']}")
    raw = catalog.store.find(src["derived_from"])
    assert raw.dataset == "storm_events_raw" and "counted" in src["method"]


def test_messy_export(tmp_path):
    f = tmp_path / "climate.csv"
    f.write_text("﻿County,Year,Average Temperature (F),Maximum Temperature (F),"
                 "Minimum Temperature (F),Precipitation (in)\n"
                 "DE WITT COUNTY,2021,\"70.1\",81.0,59.2,\n"
                 "Atlantis,2021,1,1,1,1\n"
                 "Bexar County,2021,warm,80,60,30\n")
    store = Store(tmp_path / "store")
    store.capture(f, "county_climate", "u", "p")
    cat = Catalog.open(store)
    r = cat.build()
    problems = sorted(i.problem for i in r.issues)
    assert problems == ["Average Temperature (F): not a number 'warm'",
                        "unknown county 'Atlantis'"]
    dewitt = cat.county_by_name("DeWitt")
    vals = {f["metric"]: f["value"] for f in cat.facts_for(dewitt.fips, 2021)}
    assert vals["avg_temp"] == 70.1 and vals["precipitation"] is None
