import pytest
from fastapi.testclient import TestClient

from resource_platform.api import create_app


@pytest.fixture(scope="module")
def client(home):
    return TestClient(create_app(home, serve_web=False))


def test_meta(client):
    m = client.get("/api/meta").json()
    assert m["synthetic"] is True and m["years"][0] == 2015 and m["counties"] == 254
    assert {d["id"] for d in m["datasets"]} == {"county_climate", "storm_events"}


def test_map_values_are_cited(client):
    values = client.get("/api/map/precipitation/2020").json()
    assert len(values) == 254
    v = values["48189"]  # Hale
    assert v["county"] == "Hale" and v["unit"] == "inches"
    src = client.get(f"/api/citations/{v['citation']}").json()
    assert src["row"]["County"] == "Hale County"


def test_county_and_similar(client):
    c = client.get("/api/counties/48029/2022").json()  # Bexar
    assert c["county"] == "Bexar" and {f["metric"] for f in c["facts"]} >= {"avg_temp", "tornado"}
    sim = client.get("/api/similar/48029/2022?k=3").json()
    assert len(sim) == 3 and all(m["fips"] != "48029" for m in sim)


def test_ask_and_log(client):
    a = client.post("/api/ask", json={"question": "rainfall in Hale County 2020"}).json()
    assert a["status"] == "answered" and a["log_id"]
    d = client.post("/api/ask", json={"question": "Why is Hale dry?"}).json()
    assert d["status"] == "declined"
    log = client.get("/api/log").json()
    assert log["intact"] and log["entries"] >= 2


def test_errors(client):
    assert client.get("/api/map/humidity/2020").status_code == 404
    assert client.get("/api/citations/deadbeef0000:L2").status_code == 404
    assert client.get("/api/similar/99999/2020").status_code == 404
    assert client.post("/api/ask", json={"question": ""}).status_code == 422


def test_concurrent_requests(client):
    """The app loads the map, a county and its similar counties at once."""
    from concurrent.futures import ThreadPoolExecutor
    paths = ["/api/map/precipitation/2022", "/api/counties/48189/2022",
             "/api/similar/48189/2022", "/api/meta"] * 10
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(lambda p: client.get(p).status_code, paths))
    assert codes == [200] * len(paths)
