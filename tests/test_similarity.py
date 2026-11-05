import math

import numpy as np
import pytest

from resource_platform.similarity import FEATURES, Encoder, Similarity, km


@pytest.fixture(scope="module")
def sim(catalog):
    return Similarity(catalog)


def test_level_vectors_are_graded():
    e = Encoder(dims=4096, levels=16)
    sim = lambda a, b: float(a.astype(int) @ b.astype(int)) / 4096  # noqa: E731
    assert sim(e.level_vectors[0], e.level_vectors[1]) > 0.9
    assert abs(sim(e.level_vectors[0], e.level_vectors[15])) < 0.1
    assert sim(e.level_vectors[0], e.level_vectors[4]) > sim(e.level_vectors[0], e.level_vectors[8])


def test_unknown_values_are_left_out_not_guessed():
    e = Encoder(dims=1024)
    m = np.array([[1.0] * len(FEATURES), [2.0] * len(FEATURES)])
    m[1, :] = math.nan
    whole, facets = e.encode(m)
    assert not whole[1].any()  # nothing known, nothing encoded
    assert all(not v[1].any() for v in facets.values())


def test_never_returns_the_county_itself(sim, catalog):
    bexar = catalog.county_by_name("Bexar")
    matches = sim.similar(bexar.fips, 2022, k=10)
    assert len(matches) == 10 and all(m.fips != bexar.fips for m in matches)
    assert all(m.year == 2022 for m in matches)
    assert matches == sorted(matches, key=lambda m: -m.score)
    assert set(matches[0].facets) == {"climate", "departure", "trend", "storm_mix",
                                      "storm_intensity"}


def test_distance():
    assert km((29.42, -98.49), (29.42, -98.49)) == 0
    assert 1050 < km((31.76, -106.49), (29.76, -95.37)) < 1120   # El Paso to Houston


def test_matches_are_much_closer_than_random_pairs(sim):
    # Weather is spatially coherent; a similar year should mostly be nearby.
    ev = sim.evaluate()
    assert ev["features"] == len(FEATURES)
    for method in ("hdc", "baseline"):
        assert ev[f"mean_km_{method}"] < 0.6 * ev["mean_km_random_pair"], method
    assert 0 < ev["top5_overlap"] < 1   # the two methods genuinely differ
