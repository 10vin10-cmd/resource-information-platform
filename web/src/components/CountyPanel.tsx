import { useEffect, useState } from "react";
import { api } from "../api";
import { formatValue } from "../format";
import type { CountyFacts, Match } from "../types";
import { CitationChip } from "./CitationChip";

interface Props {
  fips: string;
  year: number;
  onSelect: (fips: string) => void;
}

export function CountyPanel({ fips, year, onSelect }: Props) {
  const [facts, setFacts] = useState<CountyFacts | null>(null);
  const [similar, setSimilar] = useState<Match[] | null>(null);
  const [similarError, setSimilarError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setFacts(null);
    setSimilar(null);
    setSimilarError(null);
    api.county(fips, year).then((f) => live && setFacts(f));
    api.similar(fips, year)
      .then((s) => live && setSimilar(s))
      .catch(() => live && setSimilarError("Not enough data this year to compare."));
    return () => {
      live = false;
    };
  }, [fips, year]);

  if (!facts) return <section className="panel"><p className="muted">Loading…</p></section>;

  return (
    <section className="panel" aria-labelledby="county-heading">
      <h2 id="county-heading">{facts.county} County, {year}</h2>
      {facts.facts.length === 0 && <p className="muted">The sources have no figures for this year.</p>}
      <dl className="facts">
        {facts.facts.map((f) => (
          <div key={f.metric} className="fact">
            <dt>{f.label}</dt>
            <dd className="num">{formatValue(f.value, f.unit)}</dd>
            <CitationChip citation={f.citation} />
          </div>
        ))}
      </dl>

      <h3>Counties with a similar year in {year}</h3>
      {similarError && <p className="muted">{similarError}</p>}
      {similar && (
        <ol className="similar">
          {similar.map((m) => {
            const [top, second] = Object.entries(m.facets);
            return (
              <li key={m.fips}>
                <button type="button" className="link" onClick={() => onSelect(m.fips)}>
                  {m.county}
                </button>
                <span className="score">{m.score.toFixed(2)}</span>
                <span className="muted">
                  most alike in {top?.[0].replaceAll("_", " ")}
                  {second ? ` and ${second[0].replaceAll("_", " ")}` : ""}
                </span>
              </li>
            );
          })}
        </ol>
      )}
      <p className="muted small">
        Similar means a similar year: climate, departure from the county's normal, trend and
        severe weather. It says nothing about causes.
      </p>
    </section>
  );
}
