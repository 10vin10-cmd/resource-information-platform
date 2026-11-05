"""Count NOAA Storm Events records into one row per county and year.

NOAA's Storm Events "details" files hold one row per event, with columns such
as STATE, YEAR, EVENT_TYPE, CZ_TYPE, CZ_NAME and DAMAGE_PROPERTY ("2.50K",
"1.2M"). The catalog reads county-year tables, so this step counts events by
type and adds up the stated property damage, for one state.

What it does not do:
  - Zone-based events (CZ_TYPE "Z", used for heat, drought and some winter
    weather) aren't tied to a county, so they are counted as skipped and
    reported, never spread across counties.
  - Event types outside the categories below are skipped and reported.
  - A county-year whose events all left damage blank gets a blank damage
    figure, not zero.

The counted file is captured with `derived_from` set to the raw capture(s), so
a citation into it still leads back to the file NOAA published.
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from resource_platform.catalog import name_key

CATEGORIES: dict[str, set[str]] = {
    "Tornado": {"Tornado"},
    "Hail": {"Hail"},
    "Flood": {"Flood", "Flash Flood"},
    "Thunderstorm Wind": {"Thunderstorm Wind"},
    "Tropical": {"Tropical Storm", "Hurricane", "Hurricane (Typhoon)", "Tropical Depression"},
    "Winter": {"Winter Storm", "Winter Weather", "Ice Storm", "Heavy Snow", "Blizzard"},
}
TYPE_TO_CATEGORY = {t: cat for cat, types in CATEGORIES.items() for t in types}
METHOD = ("county events (CZ_TYPE C) counted by type and year; property damage summed "
          "from DAMAGE_PROPERTY; zone events and other types skipped")

DAMAGE = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*([KMB]?)\s*$", re.IGNORECASE)
SCALE = {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}


def parse_damage(text: str | None) -> float | None:
    """'2.50K' -> 2500.0; blank -> None (not stated); unreadable -> None."""
    if not text or not text.strip():
        return None
    m = DAMAGE.match(text)
    if not m:
        return None
    return float(m.group(1)) * SCALE[m.group(2).upper()]


@dataclass
class CountResult:
    rows: int = 0
    counted: int = 0
    skipped: Counter = field(default_factory=Counter)


def count_events(details: list[Path], out: Path, state: str, counties: list[str],
                 years: list[int] | None = None) -> CountResult:
    """Write the county-year table for `state` (e.g. "TEXAS"). Every county in
    `counties` gets a row for every year seen, so zero means no event of that
    type was recorded, not missing data."""
    result = CountResult()
    canon = {name_key(n): n for n in counties}
    counts: dict[tuple[str, int], Counter] = defaultdict(Counter)
    damage: dict[tuple[str, int], float] = {}
    seen_years: set[int] = set()
    for path in details:
        with path.open(newline="", encoding="utf-8-sig") as fh:
            for rec in csv.DictReader(fh):
                result.rows += 1
                if (rec.get("STATE") or "").strip().upper() != state.upper():
                    continue
                year = int(rec["YEAR"])
                seen_years.add(year)
                if (rec.get("CZ_TYPE") or "").strip().upper() != "C":
                    result.skipped["zone event (not tied to a county)"] += 1
                    continue
                category = TYPE_TO_CATEGORY.get((rec.get("EVENT_TYPE") or "").strip())
                if category is None:
                    result.skipped[f"type {rec.get('EVENT_TYPE')!r}"] += 1
                    continue
                raw = (rec.get("CZ_NAME") or "").strip()
                key = (canon.get(name_key(raw), raw.title()), year)
                counts[key][category] += 1
                d = parse_damage(rec.get("DAMAGE_PROPERTY"))
                if d is not None:
                    damage[key] = damage.get(key, 0.0) + d
                result.counted += 1

    header = ["County", "Year", *CATEGORIES, "Property Damage (USD)"]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        keys = set(counts) | {
            (c, y) for c in counties for y in (years or sorted(seen_years))}
        for county, year in sorted(keys, key=lambda k: (k[0], k[1])):
            c = counts.get((county, year), Counter())
            d = damage.get((county, year))
            w.writerow([county, year, *(c[cat] for cat in CATEGORIES),
                        "" if d is None else f"{d:.0f}"])
    return result


def capture_counts(store, details: list[Path], work_dir: Path, state: str = "TEXAS",
                   synthetic: bool = False, source_url: str | None = None):
    """Capture the raw details files, count them, and capture the counted
    table with `derived_from` naming the raw captures. Returns
    (raw captures, counted capture, CountResult)."""
    from resource_platform.catalog import load_counties, load_datasets

    ds = load_datasets()["storm_events"]
    url = source_url or ds.source_url
    prefix = "Synthetic sample shaped like: " if synthetic else ""
    raw = [store.capture(p, "storm_events_raw", f"synthetic://{p.name}" if synthetic else url,
                         prefix + ds.publisher, synthetic=synthetic) for p in details]
    out = work_dir / "storm_events_by_county.csv"
    result = count_events([store.path(c.digest) for c in raw], out, state,
                          [c.name for c in load_counties().values()])
    counted = store.capture(out, "storm_events", f"synthetic://{out.name}" if synthetic else url,
                            prefix + ds.publisher, synthetic=synthetic,
                            derived_from=",".join(c.digest for c in raw), method=METHOD)
    return raw, counted, result
