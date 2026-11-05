import csv

from resource_platform.storms import count_events, parse_damage

HEADER = "STATE,YEAR,EVENT_TYPE,CZ_TYPE,CZ_NAME,DAMAGE_PROPERTY\n"


def test_damage_strings():
    assert parse_damage("2.50K") == 2500
    assert parse_damage("1.2M") == 1_200_000
    assert parse_damage("0.00K") == 0
    assert parse_damage("") is None and parse_damage("lots") is None


def test_counting(tmp_path):
    raw = tmp_path / "details.csv"
    raw.write_text(HEADER +
                   "TEXAS,2021,Tornado,C,HARRIS,10.00K\n"
                   "TEXAS,2021,Flash Flood,C,HARRIS,1.5M\n"
                   "TEXAS,2021,Flood,C,HARRIS,\n"
                   "TEXAS,2021,Excessive Heat,Z,HARRIS,\n"      # zone: not a county
                   "TEXAS,2021,Dust Devil,C,HARRIS,0.00K\n"     # outside the categories
                   "TEXAS,2021,Hail,C,DE WITT,\n"               # damage left blank
                   "OKLAHOMA,2021,Tornado,C,TULSA,5.00K\n")     # another state
    out = tmp_path / "counted.csv"
    r = count_events([raw], out, "TEXAS", ["Harris", "DeWitt", "Bexar"])
    assert r.counted == 4
    assert r.skipped["zone event (not tied to a county)"] == 1
    assert r.skipped["type 'Dust Devil'"] == 1
    rows = {row["County"]: row for row in csv.DictReader(out.open())}
    assert rows["Harris"]["Tornado"] == "1" and rows["Harris"]["Flood"] == "2"
    assert rows["Harris"]["Property Damage (USD)"] == "1510000"
    assert rows["DeWitt"]["Hail"] == "1"
    assert rows["DeWitt"]["Property Damage (USD)"] == ""   # blank, not zero
    assert rows["Bexar"]["Tornado"] == "0"                 # no event recorded
    assert "Tulsa" not in rows
