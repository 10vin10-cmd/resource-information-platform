from resource_platform.capture import Store
from resource_platform.catalog import Catalog, name_key, parse_number


def test_numbers_blanks_and_markers():
    assert parse_number("12,345") == (12345.0, True)
    assert parse_number("") == (None, True)        # unknown, not an error
    assert parse_number("*") == (None, True)
    assert parse_number("n.d.") == (None, False)   # an error, reported


def test_county_name_variants():
    assert name_key("De Witt") == name_key("DEWITT") == name_key("DeWitt County")


def test_sample_loads_and_total_row_is_an_issue(catalog):
    n = catalog.db.execute("SELECT count(*) FROM facts").fetchone()[0]
    assert n > 15_000
    issues = catalog.db.execute("SELECT problem FROM load_issues").fetchall()
    assert issues == [("unknown county 'STATE TOTAL'",)]
    # every Texas county is present
    assert catalog.db.execute("SELECT count(DISTINCT fips) FROM facts").fetchone()[0] == 254


def test_blanks_stay_unknown(catalog):
    nulls = catalog.db.execute("SELECT count(*) FROM facts WHERE value IS NULL").fetchone()[0]
    assert nulls > 0  # the sample leaves some figures blank on purpose


def test_citation_resolves_to_the_source_line(catalog):
    bexar = catalog.county_by_name("Bexar")
    fact = catalog.facts_for(bexar.fips, 2020, ["municipal"])[0]
    src = catalog.resolve(f"{fact['capture'][:12]}:L{fact['line']}")
    assert src["row"]["County"] == "BEXAR" and src["row"]["Year"] == "2020"
    assert float(src["row"]["Municipal"].replace(",", "")) == fact["value"]
    assert src["synthetic"] is True and len(src["sha256"]) == 64


def test_messy_publisher_file(tmp_path):
    f = tmp_path / "wu.csv"
    f.write_text("﻿County,Year,Population,Municipal,Manufacturing,Mining,Steam Electric,"
                 "Irrigation,Livestock,Groundwater Share\n"
                 "DE WITT,2021,\"20,001\",\"1,200\",0,,0,500,*,40.0\n"
                 "Atlantis,2021,1,1,1,1,1,1,1,1\n"
                 "Bexar,2021,2000000,lots,0,0,0,0,0,10\n")
    store = Store(tmp_path / "store")
    store.capture(f, "water_use", "u", "p")
    cat = Catalog.open(store)
    r = cat.build()
    problems = sorted(i.problem for i in r.issues)
    assert problems == ["Municipal: not a number 'lots'", "unknown county 'Atlantis'"]
    dewitt = cat.county_by_name("DeWitt")
    vals = {f["metric"]: f["value"] for f in cat.facts_for(dewitt.fips, 2021)}
    assert vals["population"] == 20001 and vals["municipal"] == 1200
    assert vals["mining"] is None and vals["livestock"] is None
