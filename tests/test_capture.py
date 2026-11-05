import os

import pytest

from resource_platform.capture import IntegrityError, Store


def test_same_bytes_are_stored_once(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("County,Year\nBexar,2020\n")
    store = Store(tmp_path / "store")
    a = store.capture(f, "county_climate", "https://example.org/a.csv", "Publisher")
    b = store.capture(f, "county_climate", "https://example.org/a.csv", "Publisher")
    assert a == b and len(store.captures()) == 1
    assert store.path(a.digest).read_text() == f.read_text()


def test_a_new_revision_is_a_new_capture(tmp_path):
    f = tmp_path / "a.csv"
    store = Store(tmp_path / "store")
    f.write_text("County,Year\nBexar,2020\n")
    first = store.capture(f, "county_climate", "u", "p")
    f.write_text("County,Year\nBexar,2021\n")
    second = store.capture(f, "county_climate", "u", "p")
    assert first.digest != second.digest
    assert store.path(first.digest).exists()  # the old revision is kept


def test_tampering_is_detected(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("County,Year\nBexar,2020\n")
    store = Store(tmp_path / "store")
    cap = store.capture(f, "county_climate", "u", "p")
    target = store.path(cap.digest)
    assert store.verify() == []
    os.chmod(target, 0o644)
    target.write_text("County,Year\nBexar,1999\n")
    assert store.verify() == [cap.digest]
    with pytest.raises(IntegrityError):
        store.open_verified(cap.digest)
