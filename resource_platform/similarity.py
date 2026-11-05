"""Which counties were in a similar situation in a given year, and why.

Each county-year becomes a feature vector in five facets (size, use mix,
intensity, trend, groundwater). Two methods compare them:

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

from resource_platform.answer import USE_CATEGORIES
from resource_platform.catalog import Catalog

FACETS: dict[str, list[str]] = {
    "size": ["log_population"],
    "use_mix": [f"share_{c}" for c in USE_CATEGORIES],
    "intensity": ["log_use_per_person"],
    "trend": ["use_change_3y", "population_change_3y"],
    "groundwater": ["groundwater_share", "depth_to_water", "depth_change_3y"],
}
FEATURES = [f for fs in FACETS.values() for f in fs]


@dataclass(frozen=True)
class Key:
    fips: str
    year: int


def build_features(catalog: Catalog) -> tuple[list[Key], np.ndarray]:
    """One row per county-year that has at least population and use data.
    NaN marks a value the sources don't give."""
    rows = catalog.query(
        "SELECT fips, year, metric, value FROM facts WHERE value IS NOT NULL").fetchall()
    data: dict[tuple[str, int], dict[str, float]] = {}
    for fips, year, metric, value in rows:
        data.setdefault((fips, year), {})[metric] = value

    def total_use(d: dict[str, float]) -> float | None:
        vals = [d[c] for c in USE_CATEGORIES if c in d]
        # Only compare like with like: a year missing a category isn't a total.
        return sum(vals) if len(vals) == len(USE_CATEGORIES) else None

    keys, matrix = [], []
    for (fips, year), d in sorted(data.items()):
        pop, use = d.get("population"), total_use(d)
        if not pop or use is None:
            continue
        before = data.get((fips, year - 3), {})
        use_before, pop_before = total_use(before), before.get("population")
        f = {
            "log_population": math.log10(pop),
            "log_use_per_person": math.log10(max(use, 1) / pop),
            "use_change_3y": math.log(max(use, 1) / max(use_before, 1)) if use_before else math.nan,
            "population_change_3y": math.log(pop / pop_before) if pop_before else math.nan,
            "groundwater_share": d.get("groundwater_share", math.nan),
            "depth_to_water": d.get("depth_to_water", math.nan),
            "depth_change_3y": (d["depth_to_water"] - before["depth_to_water"])
            if "depth_to_water" in d and "depth_to_water" in before else math.nan,
        }
        for c in USE_CATEGORIES:
            f[f"share_{c}"] = d[c] / use if use else math.nan
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

    def evaluate(self, k: int = 10) -> dict:
        """Two checks that need no labels:
          self-match   a county's nearest neighbour across all county-years is
                       the same county in another year (situations persist)
          overlap      how many top-k neighbours the two methods share; low
                       overlap means a reviewer comparing them learns something
        """
        n = len(self.keys)
        fips = np.array([key.fips for key in self.keys])
        result = {"county_years": n, "features": len(FEATURES)}
        for name, sims in (("hdc", self.hdc), ("baseline", self.base)):
            s = sims.copy()
            np.fill_diagonal(s, -np.inf)
            nearest = s.argmax(axis=1)
            result[f"self_match_{name}"] = round(float((fips[nearest] == fips).mean()), 4)
        overlaps = []
        for i in range(n):
            mask = fips != fips[i]
            a = set(np.where(mask)[0][np.argsort(-self.hdc[i][mask])[:k]])
            b = set(np.where(mask)[0][np.argsort(-self.base[i][mask])[:k]])
            overlaps.append(len(a & b) / k)
        result[f"top{k}_overlap"] = round(float(np.mean(overlaps)), 4)
        return result
