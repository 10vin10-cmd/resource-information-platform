"""Which counties were in a similar situation in a given year, and why.

Each county-year becomes a feature vector in five facets (climate, departure
from the county's normal, trend, storm mix, storm intensity). Two methods
compare them:

  hyperdimensional encoder   Each feature value is quantised by its rank into
                             one of 16 levels. Level vectors are random +1/-1
                             vectors of 8,192 dimensions where nearby levels
                             share most of their signs. A feature is "bound"
                             to its level by elementwise multiplication with a
                             random feature-ID vector, and the bound vectors
                             are summed into one vector per facet and one for
                             the whole county-year. Unknown values are left
                             out of the sum rather than guessed.
  baseline                   Cosine similarity of z-scored features, unknowns
                             set to the mean.

The encoder also explains a match: each facet has its own vector, so the
per-facet similarities say which part of the picture two counties share.

This is description, not inference: similar situations, not causes or
predictions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from resource_platform.answer import EVENT_TYPES
from resource_platform.catalog import Catalog

FACETS: dict[str, list[str]] = {
    "climate": ["avg_temp", "temp_range", "log_precipitation"],
    "departure": ["temp_departure", "precip_departure"],
    "trend": ["temp_change_3y", "precip_change_3y"],
    "storm_mix": [f"share_{t}" for t in EVENT_TYPES],
    "storm_intensity": ["log_events", "log_damage"],
}
FEATURES = [f for fs in FACETS.values() for f in fs]


@dataclass(frozen=True)
class Key:
    fips: str
    year: int


def build_features(catalog: Catalog) -> tuple[list[Key], np.ndarray]:
    """One row per county-year with temperature and precipitation. NaN marks
    a value the sources don't give. Departures compare a year with the same
    county's average over the years loaded."""
    rows = catalog.query(
        "SELECT fips, year, metric, value FROM facts WHERE value IS NOT NULL").fetchall()
    data: dict[tuple[str, int], dict[str, float]] = {}
    for fips, year, metric, value in rows:
        data.setdefault((fips, year), {})[metric] = value

    normal_t: dict[str, list[float]] = {}
    normal_p: dict[str, list[float]] = {}
    for (fips, _), d in data.items():
        if "avg_temp" in d:
            normal_t.setdefault(fips, []).append(d["avg_temp"])
        if d.get("precipitation"):
            normal_p.setdefault(fips, []).append(d["precipitation"])

    def events(d: dict[str, float]) -> float | None:
        vals = [d[t] for t in EVENT_TYPES if t in d]
        return sum(vals) if len(vals) == len(EVENT_TYPES) else None

    keys, matrix = [], []
    for (fips, year), d in sorted(data.items()):
        temp, rain = d.get("avg_temp"), d.get("precipitation")
        if temp is None or not rain:
            continue
        before = data.get((fips, year - 3), {})
        n_events = events(d)
        f = {
            "avg_temp": temp,
            "temp_range": d["max_temp"] - d["min_temp"]
            if "max_temp" in d and "min_temp" in d else math.nan,
            "log_precipitation": math.log(rain),
            "temp_departure": temp - float(np.mean(normal_t[fips])),
            "precip_departure": math.log(rain / float(np.mean(normal_p[fips]))),
            "temp_change_3y": temp - before["avg_temp"] if "avg_temp" in before else math.nan,
            "precip_change_3y": math.log(rain / before["precipitation"])
            if before.get("precipitation") else math.nan,
            "log_events": math.log1p(n_events) if n_events is not None else math.nan,
            "log_damage": math.log1p(d["property_damage"])
            if "property_damage" in d else math.nan,
        }
        for t in EVENT_TYPES:
            f[f"share_{t}"] = d[t] / n_events if n_events else math.nan
        keys.append(Key(fips, year))
        matrix.append([f[name] for name in FEATURES])
    return keys, np.array(matrix, dtype=float)


class Encoder:
    def __init__(self, dims: int = 8192, levels: int = 16, seed: int = 20261105):
        self.dims, self.levels = dims, levels
        rng = np.random.default_rng(seed)
        self.ids = {f: rng.choice([-1, 1], dims).astype(np.int8) for f in FEATURES}
        # Level vectors: start random, flip a fresh block of positions at each
        # step, so level 0 and the top level are close to orthogonal and
        # neighbouring levels are nearly identical.
        base = rng.choice([-1, 1], dims).astype(np.int8)
        order = rng.permutation(dims)
        per_step = dims // (2 * (levels - 1))
        self.level_vectors = []
        for i in range(levels):
            v = base.copy()
            v[order[: i * per_step]] *= -1
            self.level_vectors.append(v)

    def quantise(self, matrix: np.ndarray) -> np.ndarray:
        """Rank of each value within its feature, as a level 0..L-1; -1 if NaN."""
        q = np.full(matrix.shape, -1, dtype=int)
        for j in range(matrix.shape[1]):
            col = matrix[:, j]
            ok = ~np.isnan(col)
            if ok.sum() == 0:
                continue
            ranks = col[ok].argsort().argsort() / max(ok.sum() - 1, 1)
            q[ok, j] = np.minimum((ranks * self.levels).astype(int), self.levels - 1)
        return q

    def encode(self, matrix: np.ndarray) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        """(whole vectors, per-facet vectors), each row a county-year, values ±1/0."""
        q = self.quantise(matrix)
        n = matrix.shape[0]
        facet_vecs = {}
        total = np.zeros((n, self.dims), dtype=np.int32)
        for facet, names in FACETS.items():
            acc = np.zeros((n, self.dims), dtype=np.int32)
            for name in names:
                j = FEATURES.index(name)
                for level in range(self.levels):
                    rows = q[:, j] == level
                    if rows.any():
                        acc[rows] += self.ids[name] * self.level_vectors[level]
            facet_vecs[facet] = np.sign(acc).astype(np.int8)
            total += acc
        return np.sign(total).astype(np.int8), facet_vecs


def cosine_matrix(v: np.ndarray) -> np.ndarray:
    v = v.astype(np.float32)
    norms = np.linalg.norm(v, axis=1, keepdims=True)
    norms[norms == 0] = 1
    u = v / norms
    return u @ u.T


def baseline_vectors(matrix: np.ndarray) -> np.ndarray:
    mean = np.nanmean(matrix, axis=0)
    std = np.nanstd(matrix, axis=0)
    std[std == 0] = 1
    z = (matrix - mean) / std
    return np.nan_to_num(z, nan=0.0)


@dataclass
class Match:
    fips: str
    county: str
    year: int
    score: float
    facets: dict[str, float]


class Similarity:
    def __init__(self, catalog: Catalog, encoder: Encoder | None = None):
        self.catalog = catalog
        self.keys, self.matrix = build_features(catalog)
        self.index = {k: i for i, k in enumerate(self.keys)}
        self.encoder = encoder or Encoder()
        whole, self.facet_vecs = self.encoder.encode(self.matrix)
        self.hdc = cosine_matrix(whole)
        self.base = cosine_matrix(baseline_vectors(self.matrix))

    def similar(self, fips: str, year: int, k: int = 5, method: str = "hdc",
                same_year: bool = True) -> list[Match]:
        """Nearest other counties (never the county itself)."""
        i = self.index.get(Key(fips, year))
        if i is None:
            raise KeyError(f"no complete data for {fips} in {year}")
        sims = (self.hdc if method == "hdc" else self.base)[i]
        order = np.argsort(-sims)
        out = []
        for j in order:
            key = self.keys[j]
            if key.fips == fips or (same_year and key.year != year):
                continue
            out.append(Match(key.fips, self.catalog.counties[key.fips].name, key.year,
                             round(float(sims[j]), 4), self.explain(i, j)))
            if len(out) == k:
                break
        return out

    def explain(self, i: int, j: int) -> dict[str, float]:
        out = {}
        for facet, vecs in self.facet_vecs.items():
            a, b = vecs[i].astype(np.int32), vecs[j].astype(np.int32)
            denom = math.sqrt(int((a * a).sum()) * int((b * b).sum())) or 1
            out[facet] = round(int((a * b).sum()) / denom, 3)
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def evaluate(self, k: int = 5) -> dict:
        """Two checks that need no labels:
          distance   weather is spatially coherent, so counties that had a
                     similar year should mostly be near each other. Mean
                     distance (km) between each county and its k same-year
                     matches, against the mean distance between random pairs.
          overlap    how many top-k matches the two methods share; low
                     overlap means a reviewer comparing them learns something
        """
        coords = {f: (c.lat, c.lon) for f, c in self.catalog.counties.items()}
        result = {"county_years": len(self.keys), "features": len(FEATURES),
                  "k": k}
        firsts: dict[str, list[set[str]]] = {"hdc": [], "baseline": []}
        for method in ("hdc", "baseline"):
            dists = []
            for key in self.keys:
                matches = self.similar(key.fips, key.year, k=k, method=method)
                firsts[method].append({m.fips for m in matches})
                dists += [km(coords[key.fips], coords[m.fips]) for m in matches]
            result[f"mean_km_{method}"] = round(float(np.mean(dists)), 1)
        fips = sorted(coords)
        pairs = [km(coords[a], coords[b]) for i, a in enumerate(fips) for b in fips[i + 1:]]
        result["mean_km_random_pair"] = round(float(np.mean(pairs)), 1)
        result[f"top{k}_overlap"] = round(float(np.mean(
            [len(a & b) / k for a, b in zip(firsts["hdc"], firsts["baseline"], strict=True)])), 4)
        return result


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lat, lon) points."""
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(h))
