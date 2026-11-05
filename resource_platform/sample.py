"""Synthetic sample data, shaped like the NOAA files the datasets describe.

The demo, tests and screenshots use this, so the project runs with no
downloads. It is generated, not real: every capture made from it is marked
synthetic, and the app and API say so next to every figure.

It writes two files:
  county_climate.csv          one row per county and year, like a Climate at
                              a Glance county export
  storm_events_details.csv    one row per event, in the column layout of the
                              Storm Events "details" files; `resource storms`
                              counts it into a county-year table

The numbers follow broad Texas patterns so the similarity search has
something real to find: rain rising from about 9 inches in the far west to
about 55 in the east, warmer in the south, hail on the High Plains, floods in
the Hill Country and the east, tropical storms on the coast (heaviest in
2017), a statewide winter storm in 2021 and a hot, dry 2022.
"""

from __future__ import annotations

import csv
import math
import random
from pathlib import Path

from resource_platform.catalog import County, load_counties

YEARS = range(2015, 2023)
SEED = 20261105

# Year-wide departures: precipitation factor and temperature anomaly (°F).
YEAR_RAIN = {2015: 1.35, 2016: 1.08, 2017: 1.0, 2018: 0.95, 2019: 1.02, 2020: 0.9,
             2021: 1.05, 2022: 0.72}
YEAR_TEMP = {2015: -0.3, 2016: 0.5, 2017: 0.6, 2018: 0.1, 2019: -0.1, 2020: 0.4,
             2021: -0.5, 2022: 1.3}


def region(c: County) -> str:
    if c.lon <= -103.5:
        return "trans_pecos"
    if c.lat >= 34.0:
        return "panhandle"
    if c.lat < 27.0:
        return "valley"
    if c.lon >= -97.8 and c.lat < 30.2:
        return "gulf"
    if c.lon >= -96.0:
        return "east"
    if c.lon <= -100.0:
        return "west"
    return "central"


# Expected events per county-year by type.
STORM_RATES = {
    "trans_pecos": dict(Tornado=0.1, Hail=1.5, Flood=0.8, Wind=1.5, Winter=0.8),
    "panhandle":   dict(Tornado=1.4, Hail=7.0, Flood=0.8, Wind=4.0, Winter=2.5),
    "west":        dict(Tornado=0.8, Hail=4.0, Flood=1.0, Wind=3.0, Winter=1.0),
    "central":     dict(Tornado=0.9, Hail=3.5, Flood=3.5, Wind=3.0, Winter=0.6),
    "east":        dict(Tornado=1.3, Hail=2.0, Flood=2.5, Wind=5.0, Winter=0.4),
    "gulf":        dict(Tornado=0.7, Hail=0.8, Flood=3.0, Wind=3.0, Winter=0.1),
    "valley":      dict(Tornado=0.2, Hail=0.6, Flood=1.5, Wind=1.5, Winter=0.05),
}
EVENT_NAMES = {"Tornado": ["Tornado"], "Hail": ["Hail"], "Flood": ["Flash Flood", "Flood"],
               "Wind": ["Thunderstorm Wind"], "Winter": ["Winter Storm", "Ice Storm"]}
TYPICAL_DAMAGE = {"Tornado": 250e3, "Hail": 40e3, "Flash Flood": 60e3, "Flood": 80e3,
                  "Thunderstorm Wind": 15e3, "Winter Storm": 20e3, "Ice Storm": 50e3,
                  "Tropical Storm": 300e3, "Hurricane": 5e6}


def poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def damage_text(rng: random.Random, typical: float) -> str:
    if rng.random() < 0.35:
        return "0.00K"
    if rng.random() < 0.05:
        return ""                          # left blank by the reporting office
    v = rng.lognormvariate(math.log(typical), 1.2)
    if v >= 1e6:
        return f"{v / 1e6:.2f}M"
    return f"{v / 1e3:.2f}K"


def generate(out_dir: Path, seed: int = SEED) -> dict[str, Path]:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    counties = sorted(load_counties().values(), key=lambda c: c.name)
    climate_rows, events = [], []
    event_id = 1_000_000
    for c in counties:
        r = region(c)
        rain0 = max(7.0, 9 + (c.lon + 106.5) / 12.5 * 46) * rng.uniform(0.9, 1.1)
        if r == "gulf":
            rain0 *= 1.1
        temp0 = 75.5 - 2.1 * (c.lat - 26) - (1.2 if c.lon <= -103 else 0) + rng.gauss(0, 0.6)
        swing = 10.5 + max(0.0, (-97 - c.lon)) * 0.55     # drier air, wider daily swing
        warming = rng.gauss(0.05, 0.02)
        for y in YEARS:
            t = y - YEARS[0]
            rain = rain0 * YEAR_RAIN[y] * rng.lognormvariate(0, 0.12)
            if y == 2017 and r == "gulf":
                rain *= 1.45                            # a slow-moving hurricane
            avg = temp0 + warming * t + YEAR_TEMP[y] + rng.gauss(0, 0.35)
            row = {"County": f"{c.name} County", "Year": y,
                   "Average Temperature (F)": f"{avg:.1f}",
                   "Maximum Temperature (F)": f"{avg + swing + rng.gauss(0, 0.3):.1f}",
                   "Minimum Temperature (F)": f"{avg - swing + rng.gauss(0, 0.3):.1f}",
                   "Precipitation (in)": f"{rain:.2f}"}
            if rng.random() < 0.012:
                row["Precipitation (in)"] = ""         # not yet reported
            climate_rows.append(row)

            def add(event_type: str, cz_type: str = "C", y: int = y, c: County = c):
                nonlocal event_id
                event_id += 1
                events.append({
                    "BEGIN_YEARMONTH": f"{y}{rng.randint(1, 12):02d}", "EVENT_ID": event_id,
                    "STATE": "TEXAS", "STATE_FIPS": 48, "YEAR": y, "EVENT_TYPE": event_type,
                    "CZ_TYPE": cz_type, "CZ_FIPS": int(c.fips[2:]), "CZ_NAME": c.name.upper(),
                    "DAMAGE_PROPERTY": damage_text(rng, TYPICAL_DAMAGE.get(event_type, 10e3)),
                })

            for kind, lam in STORM_RATES[r].items():
                if kind == "Winter" and y == 2021:
                    lam += 2.0                          # statewide February freeze
                if kind == "Flood":
                    lam *= YEAR_RAIN[y]
                for _ in range(poisson(rng, lam)):
                    add(rng.choice(EVENT_NAMES[kind]))
            if r == "gulf":
                lam = {2017: 3.0, 2020: 1.2}.get(y, 0.3)
                for _ in range(poisson(rng, lam)):
                    add("Hurricane" if y == 2017 and rng.random() < 0.5 else "Tropical Storm")
            if rng.random() < 0.3:
                add("Excessive Heat", cz_type="Z")      # zone events: skipped by the counter
            if rng.random() < 0.05:
                add("Dust Devil")                       # a type outside the categories
    # Exports often end with a statewide row; the loader must not take it for
    # a county.
    climate_rows.append({"County": "Texas statewide", "Year": 2022,
                         "Average Temperature (F)": "66.9", "Maximum Temperature (F)": "",
                         "Minimum Temperature (F)": "", "Precipitation (in)": "19.41"})
    paths = {"county_climate": out_dir / "county_climate.csv",
             "storm_events_raw": out_dir / "storm_events_details.csv"}
    _write(paths["county_climate"], climate_rows)
    _write(paths["storm_events_raw"], events)
    return paths


def _write(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def capture_sample(store, work_dir: Path) -> list:
    """Generate the sample, capture it, and count the raw storm events into
    the county-year table, exactly as `resource storms` does for real files."""
    from resource_platform.catalog import load_datasets
    from resource_platform.storms import capture_counts

    datasets = load_datasets()
    paths = generate(work_dir)
    climate = store.capture(paths["county_climate"], "county_climate",
                            f"synthetic://{paths['county_climate'].name}",
                            f"Synthetic sample shaped like: {datasets['county_climate'].publisher}",
                            synthetic=True)
    raw, counted, _ = capture_counts(store, [paths["storm_events_raw"]], work_dir,
                                     synthetic=True)
    return [climate, *raw, counted]
