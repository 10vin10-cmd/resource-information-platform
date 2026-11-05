"""Answer a question with cited figures, or say plainly why not.

Every answer has one of four outcomes:

    answered   every figure asked for was found; each one is cited
    partial    some were found (cited), the rest are listed as missing
    unknown    the question is in scope, but the sources have no figure for it
    declined   the question is out of scope: forecasts, causes, advice, or
               something the platform can't place (an unknown county)

Rules the answers follow:
  - A figure is quoted as the source stated it, with its unit and citation.
  - Nothing is added up, averaged or filled in. Asking for "total water use"
    returns each category the source reports, not a sum it never stated.
  - Every answer, including unknowns and refusals, is appended to a
    hash-chained log, so what was answered (and what couldn't be) is auditable,
    and the unanswered questions show which sources to capture next.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from resource_platform.catalog import Catalog, County, cite

USE_CATEGORIES = ["municipal", "manufacturing", "mining", "steam_electric", "irrigation",
                  "livestock"]

METRIC_WORDS: list[tuple[str, list[str]]] = [
    (r"\bdepth to (ground)?water|\bwater table|\bgroundwater levels?|\baquifer levels?"
     r"|\bwater levels?", ["depth_to_water"]),
    (r"\bwells? measured|\bhow many wells", ["wells_measured"]),
    (r"\bshare (of|from) groundwater|\bgroundwater share|\bfrom groundwater",
     ["groundwater_share"]),
    (r"\birrigat", ["irrigation"]),
    (r"\bmunicipal|\bcities\b|\bcity\b|\bpublic supply|\bdrinking", ["municipal"]),
    (r"\bmanufactur|\bindustr", ["manufacturing"]),
    (r"\bmining\b|\boil\b|\bgas\b|\bfrack", ["mining"]),
    (r"\bpower\b|\bsteam\b|\belectric", ["steam_electric"]),
    (r"\blivestock|\bcattle\b|\branch", ["livestock"]),
    (r"\bpopulation|\bpeople\b|\bresidents\b", ["population"]),
]
ALL_USE = r"\bwater use|\buse[sd]? (?:\w+ )?water|\bwater usage|\btotal\b|\bhow much water"

# County names that are also ordinary words count only when capitalised or
# followed by "County"; names shared with aquifers and rivers ("Edwards
# Aquifer", "Brazos River") don't count when followed by those words.
COMMON_WORDS = {"real", "young", "hall", "king", "wood", "bell", "hill", "lamb", "clay", "rains",
                "brown", "jack", "live oak", "wise", "gray", "ward", "hood", "lee", "kent", "coke",
                "crane", "orange", "liberty", "victoria", "cotton", "mills", "frio", "starr",
                "martin", "mason", "terry", "houston", "trinity", "garza"}

DECLINE = [
    ("cause", r"\bwhy\b|\bcause[sd]?\b|\bbecause\b|\bdue to\b|\bblame\b",
     "The platform reports what sources state. It doesn't explain causes."),
    ("forecast", r"\bwill\b|\bforecast|\bpredict|\bprojection|\bnext year\b|\bfuture\b",
     "The platform reports recorded figures only. It doesn't forecast."),
    ("advice", r"\bshould\b|\brecommend|\bbest\b|\benough\b|\ballowed\b|\bpermit(ted)?\b|\bsafe\b",
     "The platform doesn't give advice or decide what is allowed or enough."),
]


@dataclass
class Statement:
    county: str
    fips: str
    year: int
    metric: str
    label: str
    value: float | None
    unit: str
    citation: str | None
    text: str


@dataclass
class Answer:
    question: str
    status: str
    statements: list[Statement] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    reason: str | None = None
    notes: list[str] = field(default_factory=list)
    synthetic: bool = False
    log_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Question:
    counties: list[County]
    metrics: list[str]
    years: list[int]
    unknown_place: str | None = None


# -- parsing -----------------------------------------------------------------------

def parse(text: str, catalog: Catalog) -> Question:
    counties = find_counties(text, catalog)
    lowered = text.lower()
    metrics: list[str] = []
    for pattern, ids in METRIC_WORDS:
        if re.search(pattern, lowered):
            metrics += [m for m in ids if m not in metrics]
    if not metrics and re.search(ALL_USE, lowered):
        metrics = list(USE_CATEGORIES)
    years = find_years(text, catalog.years())
    unknown = None
    if not counties:
        m = re.search(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+)?) [Cc]ounty\b", text)
        unknown = m.group(1) if m else None
    return Question(counties, metrics, years, unknown)


def find_counties(text: str, catalog: Catalog) -> list[County]:
    """County names in the order they appear, longest names matched first so
    'El Paso' wins over a shorter overlapping name."""
    found: list[tuple[int, County]] = []
    taken: list[tuple[int, int]] = []
    for c in sorted(catalog.counties.values(), key=lambda c: -len(c.name)):
        pattern = re.escape(c.name).replace(r"\ ", r"\s+")
        for m in re.finditer(rf"\b{pattern}\b(\s+county\b)?(\s+(?:aquifer|river|basin)\b)?",
                             text, flags=re.IGNORECASE):
            if m.group(2):
                continue
            if c.name.lower() in COMMON_WORDS and not (m.group(0)[0].isupper() or m.group(1)):
                continue
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), c))
    return [c for _, c in sorted(found, key=lambda x: x[0])]


def find_years(text: str, available: list[int]) -> list[int]:
    latest = max(available) if available else None
    m = re.search(r"\b((?:19|20)\d\d)\s*(?:-|–|to|through|and)\s*((?:19|20)\d\d)\b", text)
    if m:
        a, b = sorted((int(m.group(1)), int(m.group(2))))
        return list(range(a, b + 1))
    m = re.search(r"\bsince\s+((?:19|20)\d\d)\b", text)
    if m and latest:
        return list(range(int(m.group(1)), latest + 1))
    years = [int(y) for y in re.findall(r"\b((?:19|20)\d\d)\b", text)]
    if years:
        return sorted(set(years))
    if re.search(r"\blatest\b|\bmost recent\b|\bcurrent\b|\bnow\b", text.lower()) and latest:
        return [latest]
    return []


# -- answering ---------------------------------------------------------------------

class Answerer:
    def __init__(self, catalog: Catalog, log: AnswerLog | None = None):
        self.catalog = catalog
        self.log = log

    def ask(self, text: str) -> Answer:
        answer = self._answer(text)
        answer.synthetic = any(self._synthetic(s.citation) for s in answer.statements)
        if self.log:
            answer.log_id = self.log.append(answer)
        return answer

    def _answer(self, text: str) -> Answer:
        for kind, pattern, message in DECLINE:
            if re.search(pattern, text.lower()):
                return Answer(text, "declined", reason=f"{kind}: {message}")
        q = parse(text, self.catalog)
        available = self.catalog.years()
        if q.years and available and max(q.years) > max(available):
            return Answer(text, "declined",
                          reason=f"forecast: the latest year on record is {max(available)}. "
                                 "The platform doesn't forecast.")
        if not q.counties:
            where = f" '{q.unknown_place} County'" if q.unknown_place else ""
            return Answer(text, "declined",
                          reason=f"place: couldn't find a Texas county{where} in the question.")
        if not q.metrics:
            return Answer(text, "declined",
                          reason="measure: the question doesn't name something the platform "
                                 "records (water use by category, population, groundwater "
                                 "levels).")
        years = q.years or available[-1:]
        if not years:
            return Answer(text, "unknown", reason="no data has been loaded yet.")

        statements, missing = [], []
        for county in q.counties:
            for year in years:
                facts = {f["metric"]: f
                         for f in self.catalog.facts_for(county.fips, year, q.metrics)}
                for metric in q.metrics:
                    _, m = self.catalog.metric(metric)
                    f = facts.get(metric)
                    if f is None or f["value"] is None:
                        why = "left blank by the source" if f else "no record"
                        missing.append(f"{m.label}, {county.name} County, {year} ({why})")
                        continue
                    statements.append(Statement(
                        county=county.name, fips=county.fips, year=year, metric=metric,
                        label=m.label, value=f["value"], unit=f["unit"],
                        citation=cite(f["capture"], f["line"]),
                        text=f"{m.label}, {county.name} County, {year}: "
                             f"{fmt(f['value'], f['unit'])}"))

        notes = []
        if q.metrics == USE_CATEGORIES:
            notes.append("Water use is reported by category. The platform doesn't add the "
                         "categories into a total the source didn't state.")
        if "depth_to_water" in q.metrics:
            for s in statements:
                wells = self.catalog.facts_for(s.fips, s.year, ["wells_measured"])
                if wells and wells[0]["value"] is not None and wells[0]["value"] < 5:
                    notes.append(f"{s.county} {s.year}: only {wells[0]['value']:.0f} wells were "
                                 "measured, so the median is unreliable.")
        if not statements:
            return Answer(text, "unknown", missing=missing, notes=notes,
                          reason="the sources have no figure for this.")
        status = "partial" if missing else "answered"
        return Answer(text, status, statements, missing, notes=notes)

    def _synthetic(self, citation: str | None) -> bool:
        if not citation:
            return False
        cap = self.catalog.store.find(citation.split(":")[0])
        return bool(cap and cap.synthetic)


def fmt(value: float, unit: str) -> str:
    if unit == "percent":
        return f"{value:.1f}%"
    if unit == "feet":
        return f"{value:,.1f} ft"
    return f"{value:,.0f} {unit}"


# -- answer log --------------------------------------------------------------------

class AnswerLog:
    """Append-only JSON Lines, each entry holding the hash of the one before.
    Editing or removing any past entry breaks every hash after it."""

    GENESIS = "0" * 64

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def append(self, answer: Answer, now: datetime | None = None) -> str:
        entries = self.entries()
        prev = entries[-1]["hash"] if entries else self.GENESIS
        body = {
            "seq": len(entries) + 1,
            "at": (now or datetime.now(UTC)).isoformat(timespec="seconds"),
            "question": answer.question,
            "status": answer.status,
            "citations": [s.citation for s in answer.statements],
            "missing": answer.missing,
            "reason": answer.reason,
            "prev": prev,
        }
        body["hash"] = _hash(body)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as fh:
            fh.write(json.dumps(body, sort_keys=True) + "\n")
        return body["hash"][:12]

    def verify(self) -> int | None:
        """Sequence number of the first broken entry, or None if intact."""
        prev = self.GENESIS
        for e in self.entries():
            stored = e.get("hash")
            body = {k: v for k, v in e.items() if k != "hash"}
            if e.get("prev") != prev or _hash(body) != stored:
                return e.get("seq", -1)
            prev = stored
        return None

    def gaps(self) -> list[tuple[str, int]]:
        """What couldn't be answered, grouped by reason, most frequent first."""
        counts: Counter[str] = Counter()
        for e in self.entries():
            if e["status"] in ("unknown", "declined"):
                counts[(e["reason"] or e["status"]).split(":")[0]] += 1
            for m in e.get("missing", []):
                counts["missing: " + m.split(",")[0]] += 1
        return counts.most_common()


def _hash(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
