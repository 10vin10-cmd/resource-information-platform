"""Synthetic sample data, shaped like the publisher files the datasets describe.

The demo, tests and screenshots use this, so the project runs with no
downloads. It is generated, not real: every capture made from it is marked
synthetic, and the app and API say so next to every figure.

The numbers follow broad regional patterns so the similarity search has
something real to find: irrigation and declining aquifers on the High Plains,
oil and gas water use in the Permian Basin, municipal demand in the metros,
industry on the Gulf Coast, livestock and power plants in East Texas.
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

from resource_platform.catalog import County, load_counties

YEARS = range(2015, 2023)
SEED = 20261105

METROS = {"Harris": 4.7e6, "Dallas": 2.6e6, "Tarrant": 2.1e6, "Bexar": 2.0e6, "Travis": 1.3e6,
          "Collin": 1.1e6, "Denton": 9.0e5, "Hidalgo": 8.7e5, "El Paso": 8.6e5, "Fort Bend": 8.2e5,
          "Montgomery": 6.2e5, "Williamson": 6.0e5, "Cameron": 4.2e5, "Brazoria": 3.7e5,
          "Bell": 3.7e5, "Galveston": 3.5e5, "Nueces": 3.5e5, "Lubbock": 3.1e5, "Webb": 2.7e5,
          "Hays": 2.4e5, "McLennan": 2.6e5, "Smith": 2.3e5, "Brazos": 2.3e5, "Jefferson": 2.5e5}
INDUSTRIAL = {"Harris", "Jefferson", "Brazoria", "Nueces", "Galveston", "Orange", "Calhoun",
              "Victoria", "Matagorda"}


def region(c: County) -> str:
    if c.name in METROS and METROS[c.name] >= 6e5:
        return "metro"
    if c.lat >= 33.6 and c.lon <= -100.0:
        return "high_plains"
    if c.lon <= -101.0 and c.lat < 33.6:
        return "permian"
    if c.lat < 26.9:
        return "valley"
    if c.lon >= -97.6 and c.lat < 30.3:
        return "gulf"
    if c.lon >= -96.2:
        return "east"
    return "central"


# Use per person (acre-feet / year) by category, groundwater share and the
# aquifer trend (feet per year, positive = water table falling).
PROFILE = {
    "metro":       dict(mun=0.16, man=0.020, min=0.002, steam=0.010, irr=0.004, liv=0.0005,
                        gw=(10, 35), decline=0.4),
    "high_plains": dict(mun=0.20, man=0.050, min=0.050, steam=0.020, irr=12.0, liv=0.60,
                        gw=(88, 99), decline=1.6),
    "permian":     dict(mun=0.22, man=0.010, min=1.80, steam=0.050, irr=1.2, liv=0.20,
                        gw=(80, 98), decline=0.9),
    "valley":      dict(mun=0.14, man=0.008, min=0.010, steam=0.010, irr=1.6, liv=0.02,
                        gw=(3, 15), decline=0.2),
    "gulf":        dict(mun=0.15, man=0.150, min=0.020, steam=0.080, irr=1.0, liv=0.05,
                        gw=(15, 45), decline=0.3),
    "east":        dict(mun=0.15, man=0.060, min=0.030, steam=0.400, irr=0.05, liv=0.25,
                        gw=(30, 60), decline=0.2),
    "central":     dict(mun=0.17, man=0.010, min=0.040, steam=0.050, irr=0.30, liv=0.30,
                        gw=(35, 75), decline=0.5),
}


def generate(out_dir: Path, seed: int = SEED) -> dict[str, Path]:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    counties = sorted(load_counties().values(), key=lambda c: c.name)
    use_rows, gw_rows = [], []
    for c in counties:
        r = region(c)
        p = PROFILE[r]
        pop0 = METROS.get(c.name) or rng.lognormvariate(9.6, 1.0)
        growth = rng.gauss(0.022 if r == "metro" else 0.004, 0.008)
        scale = {k: rng.lognormvariate(0, 0.35)
                 for k in ("mun", "man", "min", "steam", "irr", "liv")}
        if c.name in INDUSTRIAL:
            scale["man"] *= 8
        gw_share = rng.uniform(*p["gw"])
        depth0 = rng.uniform(40, 120) if r != "high_plains" else rng.uniform(150, 320)
        decline = rng.gauss(p["decline"], 0.4)
        wells = max(1, int(rng.lognormvariate(2.6 if r == "high_plains" else 2.0, 0.7)))
        for y in YEARS:
            t = y - YEARS[0]
            drought = 1.25 if y in (2018, 2022) else 1.0   # dry years use more
            pop = pop0 * (1 + growth) ** t
            vals = {
                "Population": round(pop),
                "Municipal": pop * p["mun"] * scale["mun"] * drought,
                "Manufacturing": (pop if r == "metro" or c.name in INDUSTRIAL else 2e4)
                * p["man"] * scale["man"],
                "Mining": (2000 + pop * 0.05) * p["min"] * scale["min"] * (1 + 0.06 * t),
                "Steam Electric": (3e4 * p["steam"] * scale["steam"]) if rng.random() < 0.35 else 0,
                "Irrigation": (8e3 * p["irr"] * scale["irr"]) * drought * (1 - 0.015 * t),
                "Livestock": (2e3 * p["liv"] * scale["liv"] + 30),
            }
            row = {"County": c.name.upper(), "Year": y}
            for k, v in vals.items():
                row[k] = f"{v * rng.uniform(0.94, 1.06):,.0f}" if k != "Population" else f"{v:,}"
            row["Groundwater Share"] = f"{min(100, max(0, gw_share + rng.gauss(0, 2))):.1f}"
            if rng.random() < 0.02:
                row["Mining"] = ""        # not reported this year
            if rng.random() < 0.01:
                row["Livestock"] = "*"    # withheld
            use_rows.append(row)

            n = max(0, wells + rng.randint(-2, 2))
            depth = depth0 + decline * t + rng.gauss(0, 1.5) + (4 if y in (2018, 2022) else 0)
            if n == 0 or rng.random() < 0.03:
                continue                  # no wells measured: no row at all
            gw_rows.append({"County": c.name, "Year": y, "Median Depth (ft)": f"{depth:.1f}",
                            "Wells Measured": n})
    # Publisher files often end with a total row; the loader must not take it
    # for a county.
    use_rows.append({"County": "STATE TOTAL", "Year": 2022, "Population": "",
                     "Municipal": "", "Manufacturing": "", "Mining": "", "Steam Electric": "",
                     "Irrigation": "", "Livestock": "", "Groundwater Share": ""})
    paths = {"water_use": out_dir / "water_use_by_county.csv",
             "groundwater_levels": out_dir / "groundwater_levels_by_county.csv"}
    _write(paths["water_use"], use_rows)
    _write(paths["groundwater_levels"], gw_rows)
    return paths


def _write(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
