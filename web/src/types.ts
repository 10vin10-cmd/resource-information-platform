export interface MetricInfo {
  id: string;
  column: string;
  unit: string;
  label: string;
}

export interface DatasetInfo {
  id: string;
  title: string;
  publisher: string;
  source_url: string;
  notes: string;
  metrics: MetricInfo[];
}

export interface Meta {
  years: number[];
  synthetic: boolean;
  datasets: DatasetInfo[];
  counties: number;
}

export interface MapValue {
  county: string;
  value: number | null;
  unit: string;
  citation: string;
}

export type MapValues = Record<string, MapValue>;

export interface CountyFact {
  metric: string;
  label: string;
  value: number | null;
  unit: string;
  citation: string;
}

export interface CountyFacts {
  fips: string;
  county: string;
  year: number;
  facts: CountyFact[];
}

export interface Match {
  fips: string;
  county: string;
  year: number;
  score: number;
  facets: Record<string, number>;
}

export interface Statement {
  county: string;
  fips: string;
  year: number;
  metric: string;
  label: string;
  value: number | null;
  unit: string;
  citation: string | null;
  text: string;
}

export type AnswerStatus = "answered" | "partial" | "unknown" | "declined";

export interface Answer {
  question: string;
  status: AnswerStatus;
  statements: Statement[];
  missing: string[];
  reason: string | null;
  notes: string[];
  synthetic: boolean;
  log_id: string | null;
}

export interface SourceLine {
  citation: string;
  dataset: string;
  title: string;
  publisher: string;
  source_url: string;
  captured_at: string;
  sha256: string;
  line: number;
  synthetic: boolean;
  row: Record<string, string>;
  derived_from: string | null;
  method: string | null;
}
