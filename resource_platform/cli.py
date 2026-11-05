"""`resource`: capture sources, build the catalog, ask questions, find similar
counties, and serve the API and map."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from resource_platform.answer import Answerer, AnswerLog
from resource_platform.capture import Store
from resource_platform.catalog import Catalog, load_datasets

HOME = Path(".resource")


def open_catalog(home: Path) -> Catalog:
    cat = Catalog.open(Store(home / "store"))
    cat.build()
    return cat


def cmd_capture(a) -> int:
    ds = load_datasets().get(a.dataset)
    if ds is None:
        print(f"unknown dataset {a.dataset}; known: {', '.join(load_datasets())}", file=sys.stderr)
        return 2
    cap = Store(a.home / "store").capture(a.file, ds.id, a.source_url or ds.source_url,
                                          ds.publisher, synthetic=a.synthetic)
    print(f"captured {a.file} as {cap.short} ({cap.size:,} bytes) for {ds.id}")
    return 0


def cmd_sample(a) -> int:
    from resource_platform.sample import capture_sample
    for cap in capture_sample(Store(a.home / "store"), a.home / "sample"):
        how = " (counted from the raw events)" if cap.derived_from else ""
        print(f"captured {cap.filename} as {cap.short} for {cap.dataset}, synthetic{how}")
    return 0


def cmd_storms(a) -> int:
    from resource_platform.storms import capture_counts
    raw, counted, r = capture_counts(Store(a.home / "store"), a.files, a.home / "work",
                                     state=a.state, source_url=a.source_url)
    print(f"captured {len(raw)} raw file(s); {r.rows:,} rows read, {r.counted:,} county events "
          f"counted into {counted.short}")
    for reason, n in r.skipped.most_common():
        print(f"  skipped {n:>6,}  {reason}")
    return 0


def cmd_build(a) -> int:
    cat = Catalog.open(Store(a.home / "store"))
    r = cat.build()
    print(f"{r.facts:,} facts loaded, {len(r.issues)} load issue(s)")
    for i in r.issues[:20]:
        print(f"  {i.capture[:12]}:L{i.line}  {i.problem}")
    return 0


def cmd_ask(a) -> int:
    cat = open_catalog(a.home)
    ans = Answerer(cat, AnswerLog(a.home / "answers.jsonl")).ask(" ".join(a.question))
    if a.json:
        print(json.dumps(ans.to_dict(), indent=2))
        return 0
    print(f"[{ans.status}]{' (synthetic data)' if ans.synthetic else ''}")
    for s in ans.statements:
        print(f"  {s.text}   [{s.citation}]")
    for m in ans.missing:
        print(f"  missing: {m}")
    if ans.reason:
        print(f"  {ans.reason}")
    for n in ans.notes:
        print(f"  note: {n}")
    return 0


def cmd_cite(a) -> int:
    print(json.dumps(open_catalog(a.home).resolve(a.citation), indent=2))
    return 0


def cmd_similar(a) -> int:
    from resource_platform.similarity import Similarity
    cat = open_catalog(a.home)
    county = cat.county_by_name(a.county)
    if county is None:
        print(f"unknown county {a.county}", file=sys.stderr)
        return 2
    sim = Similarity(cat)
    if a.evaluate:
        print(json.dumps(sim.evaluate(), indent=2))
    for m in sim.similar(county.fips, a.year, k=a.k, method=a.method) if a.k > 0 else []:
        top = ", ".join(f"{f} {v:.2f}" for f, v in list(m.facets.items())[:2])
        print(f"  {m.county:<14} {m.score:.3f}   shared most: {top}")
    return 0


def cmd_log(a) -> int:
    log = AnswerLog(a.home / "answers.jsonl")
    broken = log.verify()
    print(f"{len(log.entries())} answers logged; chain "
          f"{'intact' if broken is None else f'BROKEN at entry {broken}'}")
    for reason, n in log.gaps():
        print(f"  {n:>4}  {reason}")
    return 0 if broken is None else 1


def cmd_serve(a) -> int:
    import uvicorn

    from resource_platform.api import create_app
    uvicorn.run(create_app(a.home), host=a.host, port=a.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="resource", description=__doc__)
    p.add_argument("--home", type=Path, default=HOME, help="data directory (default .resource)")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("capture", help="capture a source file by digest")
    c.add_argument("dataset")
    c.add_argument("file", type=Path)
    c.add_argument("--source-url")
    c.add_argument("--synthetic", action="store_true")
    c.set_defaults(fn=cmd_capture)

    sub.add_parser("sample", help="generate and capture the synthetic sample").set_defaults(
        fn=cmd_sample)
    c = sub.add_parser("storms", help="count NOAA Storm Events details files per county-year")
    c.add_argument("files", nargs="+", type=Path)
    c.add_argument("--state", default="TEXAS")
    c.add_argument("--source-url")
    c.set_defaults(fn=cmd_storms)

    sub.add_parser("build", help="load the latest captures and report issues").set_defaults(
        fn=cmd_build)

    c = sub.add_parser("ask", help="ask a question")
    c.add_argument("question", nargs="+")
    c.add_argument("--json", action="store_true")
    c.set_defaults(fn=cmd_ask)

    c = sub.add_parser("cite", help="show the source line behind a citation")
    c.add_argument("citation")
    c.set_defaults(fn=cmd_cite)

    c = sub.add_parser("similar", help="counties in a similar situation")
    c.add_argument("county")
    c.add_argument("year", type=int)
    c.add_argument("-k", type=int, default=5, help="neighbours to list (0: none)")
    c.add_argument("--method", choices=["hdc", "baseline"], default="hdc")
    c.add_argument("--evaluate", action="store_true")
    c.set_defaults(fn=cmd_similar)

    sub.add_parser("log", help="verify the answer log and list what went unanswered"
                   ).set_defaults(fn=cmd_log)

    c = sub.add_parser("serve", help="API and map on one port")
    c.add_argument("--host", default="127.0.0.1")
    c.add_argument("--port", type=int, default=8000)
    c.set_defaults(fn=cmd_serve)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
