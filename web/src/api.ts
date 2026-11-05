import type { Answer, CountyFacts, MapValues, Match, Meta, SourceLine } from "./types";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return (await res.json()) as T;
}

export const api = {
  meta: () => get<Meta>("api/meta"),
  map: (metric: string, year: number) => get<MapValues>(`api/map/${metric}/${year}`),
  county: (fips: string, year: number) => get<CountyFacts>(`api/counties/${fips}/${year}`),
  similar: (fips: string, year: number) => get<Match[]>(`api/similar/${fips}/${year}?k=5`),
  citation: (id: string) => get<SourceLine>(`api/citations/${encodeURIComponent(id)}`),
  ask: async (question: string): Promise<Answer> => {
    const res = await fetch("api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    return (await res.json()) as Answer;
  },
};
