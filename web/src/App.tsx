import type { FeatureCollection, Geometry } from "geojson";
import { useEffect, useMemo, useState } from "react";
import { feature } from "topojson-client";
import type { GeometryCollection, Topology } from "topojson-specification";
import { api } from "./api";
import { AskBox } from "./components/AskBox";
import { CountyMap } from "./components/CountyMap";
import { CountyPanel } from "./components/CountyPanel";
import { quantileBreaks } from "./format";
import type { MapValues, Meta, MetricInfo } from "./types";

type Counties = FeatureCollection<Geometry, { name: string }>;

export function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [counties, setCounties] = useState<Counties | null>(null);
  const [metric, setMetric] = useState("precipitation");
  const [year, setYear] = useState<number | null>(null);
  const [values, setValues] = useState<MapValues>({});
  const [selected, setSelected] = useState<string | null>(
    new URLSearchParams(window.location.search).get("county"));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.meta().then((m) => {
      setMeta(m);
      setYear(m.years[m.years.length - 1] ?? null);
    }).catch((e) => setError(String(e)));
    fetch("texas-counties.json")
      .then((r) => r.json() as Promise<Topology<{ counties: GeometryCollection<{ name: string }> }>>)
      .then((topo) => setCounties(feature(topo, topo.objects.counties) as Counties))
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (year !== null) api.map(metric, year).then(setValues).catch((e) => setError(String(e)));
  }, [metric, year]);

  const metrics: MetricInfo[] = useMemo(
    () => meta?.datasets.flatMap((d) => d.metrics) ?? [], [meta]);
  const current = metrics.find((m) => m.id === metric);
  const breaks = useMemo(() => quantileBreaks(
    Object.values(values).map((v) => v.value).filter((v): v is number => v !== null)), [values]);
  const sortedCounties = useMemo(() => counties?.features
    .map((f) => ({ fips: String(f.id), name: f.properties.name }))
    .sort((a, b) => a.name.localeCompare(b.name)) ?? [], [counties]);

  if (error) return <main><p className="error" role="alert">Couldn't load the platform: {error}</p></main>;
  if (!meta || !counties || year === null) return <main><p className="muted">Loading…</p></main>;

  return (
    <main>
      <header>
        <div>
          <h1>Resource Information Platform</h1>
          <p className="muted">
            Texas county weather: temperature, rainfall and severe weather, quoted from NOAA
            records with a citation for every figure.
          </p>
        </div>
        {meta.synthetic && (
          <p className="banner" role="note">
            Synthetic sample data, generated to resemble the publisher files. Capture the real
            files with <code>resource capture</code> for real figures.
          </p>
        )}
      </header>

      <div className="controls">
        <label>
          Measure
          <select value={metric} onChange={(e) => setMetric(e.target.value)}>
            {meta.datasets.map((d) => (
              <optgroup key={d.id} label={d.title}>
                {d.metrics.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
              </optgroup>
            ))}
          </select>
        </label>
        <label>
          Year
          <select value={year} onChange={(e) => setYear(Number(e.target.value))}>
            {meta.years.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </label>
        <label>
          County
          <select value={selected ?? ""} onChange={(e) => setSelected(e.target.value || null)}>
            <option value="">Choose a county…</option>
            {sortedCounties.map((c) => <option key={c.fips} value={c.fips}>{c.name}</option>)}
          </select>
        </label>
      </div>

      <div className="layout">
        <CountyMap counties={counties} values={values} breaks={breaks}
                   unit={current?.unit ?? ""} selected={selected} onSelect={setSelected} />
        <div className="side">
          {selected
            ? <CountyPanel fips={selected} year={year} onSelect={setSelected} />
            : <section className="panel"><p className="muted">Select a county on the map to see
                its figures, their sources, and the counties most like it.</p></section>}
          <AskBox />
        </div>
      </div>
    </main>
  );
}
