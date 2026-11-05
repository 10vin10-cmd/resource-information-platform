/** Values are shown exactly as the source states them, with their unit. */
export function formatValue(value: number | null, unit: string): string {
  if (value === null) return "no figure";
  if (unit === "percent") return `${value.toFixed(1)}%`;
  if (unit === "feet") return `${value.toLocaleString("en-US", { maximumFractionDigits: 1 })} ft`;
  return `${Math.round(value).toLocaleString("en-US")} ${unit}`;
}

/** Class breaks at quantiles of the known values (unknowns excluded). */
export function quantileBreaks(values: number[], classes = 5): number[] {
  const sorted = [...values].sort((a, b) => a - b);
  if (sorted.length === 0) return [];
  const breaks: number[] = [];
  for (let i = 1; i < classes; i++) {
    const idx = Math.min(sorted.length - 1, Math.floor((i / classes) * sorted.length));
    const b = sorted[idx]!;
    if (breaks.length === 0 || b > breaks[breaks.length - 1]!) breaks.push(b);
  }
  return breaks;
}

/** Index of the class a value falls in, or -1 for an unknown value. */
export function classOf(value: number | null, breaks: number[]): number {
  if (value === null) return -1;
  let i = 0;
  while (i < breaks.length && value >= breaks[i]!) i++;
  return i;
}

export function compact(value: number): string {
  return value.toLocaleString("en-US", { notation: "compact", maximumFractionDigits: 1 });
}
