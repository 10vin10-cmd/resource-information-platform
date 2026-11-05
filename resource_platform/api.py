"""HTTP API, and the built map app on the same port.

    GET  /api/meta                       datasets, metrics, years, synthetic flag
    GET  /api/map/{metric}/{year}        one value per county, each cited
    GET  /api/counties/{fips}/{year}     every fact for a county-year, cited
    GET  /api/similar/{fips}/{year}      similar counties with per-facet scores
    POST /api/ask      {"question": ...} cited answer, or why not
    GET  /api/citations/{citation}       the source line, re-read and digest-checked
    GET  /api/log                        answer-log integrity and unanswered questions
"""

from __future__ import annotations

from dataclasses import asdict
from functools import cached_property
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from resource_platform.answer import Answerer, AnswerLog
from resource_platform.capture import Store
from resource_platform.catalog import Catalog, cite

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class State:
    def __init__(self, home: Path):
        self.home = home
        self.catalog = Catalog.open(Store(home / "store"))
        self.catalog.build()
        self.log = AnswerLog(home / "answers.jsonl")
        self.answerer = Answerer(self.catalog, self.log)

    @cached_property
    def similarity(self):
        from resource_platform.similarity import Similarity
        return Similarity(self.catalog)


def create_app(home: Path, serve_web: bool = True) -> FastAPI:
    app = FastAPI(title="Resource Information Platform", version="1.0.0")
    state = State(home)

    def county_or_404(fips: str):
        c = state.catalog.counties.get(fips)
        if c is None:
            raise HTTPException(404, f"unknown county {fips}")
        return c

    @app.get("/api/meta")
    def meta():
        caps = state.catalog.store.captures()
        return {
            "years": state.catalog.years(),
            "synthetic": any(c.synthetic for c in caps),
            "datasets": [{
                "id": ds.id, "title": ds.title, "publisher": ds.publisher,
                "source_url": ds.source_url, "notes": ds.notes,
                "metrics": [asdict(m) for m in ds.metrics],
            } for ds in state.catalog.datasets.values()],
            "counties": len(state.catalog.counties),
        }

    @app.get("/api/map/{metric}/{year}")
    def map_values(metric: str, year: int):
        if state.catalog.metric(metric) is None:
            raise HTTPException(404, f"unknown metric {metric}")
        return state.catalog.metric_by_county(metric, year)

    @app.get("/api/counties/{fips}/{year}")
    def county(fips: str, year: int):
        c = county_or_404(fips)
        facts = state.catalog.facts_for(fips, year)
        return {"fips": fips, "county": c.name, "year": year, "facts": [{
            "metric": f["metric"], "label": state.catalog.metric(f["metric"])[1].label,
            "value": f["value"], "unit": f["unit"], "citation": cite(f["capture"], f["line"]),
        } for f in facts]}

    @app.get("/api/similar/{fips}/{year}")
    def similar(fips: str, year: int, k: int = 5, method: str = "hdc"):
        county_or_404(fips)
        if method not in ("hdc", "baseline"):
            raise HTTPException(400, "method is hdc or baseline")
        try:
            return [asdict(m) for m in state.similarity.similar(fips, year, k=min(k, 20),
                                                                method=method)]
        except KeyError as e:
            raise HTTPException(404, str(e.args[0])) from e

    @app.post("/api/ask")
    def ask(req: AskRequest):
        return state.answerer.ask(req.question).to_dict()

    @app.get("/api/citations/{citation}")
    def citation(citation: str):
        try:
            return state.catalog.resolve(citation)
        except KeyError as e:
            raise HTTPException(404, f"no such citation {citation}") from e

    @app.get("/api/log")
    def log():
        broken = state.log.verify()
        return {"entries": len(state.log.entries()), "intact": broken is None,
                "broken_at": broken, "unanswered": state.log.gaps()}

    if serve_web and WEB_DIST.exists():
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
    return app
