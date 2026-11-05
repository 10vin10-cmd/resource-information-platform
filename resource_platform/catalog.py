"""Turn captured files into one queryable table of facts.

A fact is a single value the source stated: (county, year, metric, value),
plus the capture digest and the line of the file it came from. Nothing is
summed, filled in or interpolated here; a blank in the source stays unknown.

Values that can't be read (unknown county names, text where a number should
be) are kept as load issues instead of being dropped silently.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import pyarrow as pa
import yaml

from resource_platform.capture import Capture, Store

ROOT = Path(__file__).resolve().parent.parent
DATASETS = ROOT / "datasets"
COUNTIES = Path(__file__).resolve().parent / "data" / "texas_counties.csv"


@dataclass(frozen=True)
class Metric:
    id: str
    column: str
    unit: str
    label: str


@dataclass(frozen=True)
class Dataset:
    id: str
    title: str
    publisher: str
    source_url: str
    notes: str
    county_column: str
    year_column: str
    metrics: tuple[Metric, ...]

    @classmethod
    def load(cls, path: Path) -> Dataset:
        raw = yaml.safe_load(path.read_text())
        return cls(
            id=raw["id"], title=raw["title"], publisher=raw["publisher"],
            source_url=raw["source_url"], notes=" ".join(str(raw.get("notes", "")).split()),
            county_column=raw["keys"]["county"], year_column=raw["keys"]["year"],
            metrics=tuple(Metric(id=k, column=v["column"], unit=v["unit"], label=v["label"])
                          for k, v in raw["metrics"].items()),
        )


def load_datasets(directory: Path = DATASETS) -> dict[str, Dataset]:
    return {d.id: d for d in (Dataset.load(p) for p in sorted(directory.glob("*.yaml")))}


@dataclass(frozen=True)
class County:
    fips: str
    name: str
    lon: float
    lat: float


def load_counties(path: Path = COUNTIES) -> dict[str, County]:
    with path.open() as fh:
        return {r["fips"]: County(r["fips"], r["name"], float(r["lon"]), float(r["lat"]))
                for r in csv.DictReader(fh)}


def name_key(name: str) -> str:
    """'De Witt', 'DEWITT' and 'DeWitt County' all match the same county."""
    key = re.sub(r"[^a-z]", "", name.lower())
    return key.removesuffix("county") or key


@dataclass
class LoadIssue:
    capture: str
    line: int
    problem: str


@dataclass
class LoadResult:
    facts: int = 0
    issues: list[LoadIssue] = field(default_factory=list)


NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


def parse_number(text: str | None) -> tuple[float | None, bool]:
    """(value, ok). Blank or a not-reported marker is (None, True): unknown,
    not an error. Anything else that isn't a number is (None, False)."""
    if text is None:
        return None, True
    t = text.strip().replace(",", "")
    if t in ("", "*", "-", "NA", "N/A", "n/a"):
        return None, True
    if NUMBER.match(t):
        return float(t), True
    return None, False


FACT_COLUMNS = [("dataset", pa.string()), ("capture", pa.string()), ("line", pa.int32()),
                ("fips", pa.string()), ("county", pa.string()), ("year", pa.int32()),
                ("metric", pa.string()), ("value", pa.float64()), ("unit", pa.string())]

SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    dataset  VARCHAR NOT NULL,
    capture  VARCHAR NOT NULL,   -- sha256 of the source file
    line     INTEGER NOT NULL,   -- line in that file (header is line 1)
    fips     VARCHAR NOT NULL,
    county   VARCHAR NOT NULL,
    year     INTEGER NOT NULL,
    metric   VARCHAR NOT NULL,
    value    DOUBLE,             -- NULL: the source left it blank
    unit     VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS load_issues (capture VARCHAR, line INTEGER, problem VARCHAR);
"""


class Catalog:
    def __init__(self, db: duckdb.DuckDBPyConnection, store: Store,
                 datasets: dict[str, Dataset], counties: dict[str, County]):
        self.db, self.store, self.datasets, self.counties = db, store, datasets, counties
        self.by_name = {name_key(c.name): c for c in counties.values()}

    @classmethod
    def open(cls, store: Store, path: str = ":memory:") -> Catalog:
        db = duckdb.connect(path)
        db.execute(SCHEMA)
        return cls(db, store, load_datasets(), load_counties())

    def build(self) -> LoadResult:
        """Load the latest capture of every dataset (rebuilding from scratch)."""
        self.db.execute("DELETE FROM facts; DELETE FROM load_issues;")
        total = LoadResult()
        for ds in self.datasets.values():
            cap = self.store.latest(ds.id)
            if cap:
                r = self.load(ds, cap)
                total.facts += r.facts
                total.issues += r.issues
        return total

    def load(self, ds: Dataset, cap: Capture) -> LoadResult:
        text = self.store.open_verified(cap.digest).decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        missing = [c for c in [ds.county_column, ds.year_column, *(m.column for m in ds.metrics)]
                   if c not in (reader.fieldnames or [])]
        result = LoadResult()
        if missing:
            result.issues.append(
                LoadIssue(cap.digest, 1, f"columns not found: {', '.join(missing)}"))
        rows = []
        for line, rec in enumerate(reader, start=2):
            county = self.by_name.get(name_key(rec.get(ds.county_column) or ""))
            if county is None:
                result.issues.append(LoadIssue(cap.digest, line,
                                               f"unknown county {rec.get(ds.county_column)!r}"))
                continue
            year, ok = parse_number(rec.get(ds.year_column))
            if year is None or not ok:
                result.issues.append(LoadIssue(cap.digest, line,
                                               f"bad year {rec.get(ds.year_column)!r}"))
                continue
            for m in ds.metrics:
                if m.column not in rec:
                    continue
                value, ok = parse_number(rec[m.column])
                if not ok:
                    result.issues.append(LoadIssue(cap.digest, line,
                                                   f"{m.column}: not a number {rec[m.column]!r}"))
                    continue
                rows.append((ds.id, cap.digest, line, county.fips, county.name, int(year), m.id,
                             value, m.unit))
        if rows:
            cols = list(zip(*rows, strict=True))
            batch = pa.table({name: pa.array(col, type=t) for (name, t), col in
                              zip(FACT_COLUMNS, cols, strict=True)})
            self.db.register("batch", batch)
            self.db.execute("INSERT INTO facts SELECT * FROM batch")
            self.db.unregister("batch")
        if result.issues:
            self.db.executemany("INSERT INTO load_issues VALUES (?, ?, ?)",
                                [(i.capture, i.line, i.problem) for i in result.issues])
        result.facts = len(rows)
        return result

    # -- lookups -------------------------------------------------------------------

    def query(self, sql: str, args: list | None = None) -> duckdb.DuckDBPyConnection:
        """Run a read on its own cursor. The API serves requests on several
        threads, and one DuckDB connection refuses overlapping calls."""
        return self.db.cursor().execute(sql, args or [])

    def metric(self, metric_id: str) -> tuple[Dataset, Metric] | None:
        for ds in self.datasets.values():
            for m in ds.metrics:
                if m.id == metric_id:
                    return ds, m
        return None

    def years(self) -> list[int]:
        return [r[0] for r in self.query(
            "SELECT DISTINCT year FROM facts ORDER BY year").fetchall()]

    def facts_for(self, fips: str, year: int, metrics: list[str] | None = None) -> list[dict]:
        sql = "SELECT * FROM facts WHERE fips = ? AND year = ?"
        args: list = [fips, year]
        if metrics:
            sql += f" AND metric IN ({', '.join('?' * len(metrics))})"
            args += metrics
        cur = self.query(sql + " ORDER BY dataset, metric", args)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]

    def metric_by_county(self, metric: str, year: int) -> dict[str, dict]:
        cur = self.query(
            "SELECT fips, county, value, unit, capture, line FROM facts "
            "WHERE metric = ? AND year = ?", [metric, year])
        return {r[0]: {"county": r[1], "value": r[2], "unit": r[3],
                       "citation": cite(r[4], r[5])} for r in cur.fetchall()}

    def county_by_name(self, name: str) -> County | None:
        return self.by_name.get(name_key(name))

    def resolve(self, citation: str) -> dict:
        """The exact source line behind a citation, re-read from the capture
        after checking its digest."""
        digest, _, line_text = citation.partition(":L")
        cap = self.store.find(digest)
        if cap is None or not line_text.isdigit():
            raise KeyError(citation)
        line = int(line_text)
        lines = self.store.open_verified(cap.digest).decode("utf-8-sig").splitlines()
        if not 2 <= line <= len(lines):
            raise KeyError(citation)
        header = next(csv.reader([lines[0]]))
        values = next(csv.reader([lines[line - 1]]))
        ds = self.datasets.get(cap.dataset)
        return {
            "citation": citation, "dataset": cap.dataset, "title": ds.title if ds else cap.dataset,
            "publisher": cap.publisher, "source_url": cap.source_url,
            "captured_at": cap.captured_at, "sha256": cap.digest, "line": line,
            "synthetic": cap.synthetic, "row": dict(zip(header, values, strict=False)),
            "derived_from": cap.derived_from, "method": cap.method,
        }


def cite(digest: str, line: int) -> str:
    """Citation id: the first 12 hex digits of the capture digest and the line."""
    return f"{digest[:12]}:L{line}"
