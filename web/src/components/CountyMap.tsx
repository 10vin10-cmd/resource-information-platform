import { geoConicConformal, geoPath } from "d3-geo";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import { useMemo } from "react";
import { classOf, compact, formatValue } from "../format";
import type { MapValues } from "../types";

interface Props {
  counties: FeatureCollection<Geometry, { name: string }>;
  values: MapValues;
  breaks: number[];
  unit: string;
  selected: string | null;
  onSelect: (fips: string) => void;
}

const WIDTH = 640;
const HEIGHT = 600;

export function CountyMap({ counties, values, breaks, unit, selected, onSelect }: Props) {
  const path = useMemo(() => {
    const projection = geoConicConformal()
      .parallels([27.5, 35])
      .rotate([100, 0])
      .fitSize([WIDTH, HEIGHT], counties);
    return geoPath(projection);
  }, [counties]);

  const selectedFeature = counties.features.find((f) => String(f.id) === selected);

  return (
    <figure className="map">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img"
           aria-label="Map of Texas counties shaded by the selected measure">
        <defs>
          <pattern id="unknown" width="6" height="6" patternUnits="userSpaceOnUse"
                   patternTransform="rotate(45)">
            <rect width="6" height="6" className="unknown-bg" />
            <line x1="0" y1="0" x2="0" y2="6" className="unknown-line" />
          </pattern>
        </defs>
        {counties.features.map((f: Feature<Geometry, { name: string }>) => {
          const fips = String(f.id);
          const v = values[fips];
          const cls = classOf(v?.value ?? null, breaks);
          return (
            <path key={fips} d={path(f) ?? undefined}
                  className={cls < 0 ? "county unknown" : `county c${cls}`}
                  onClick={() => onSelect(fips)}>
              <title>{`${f.properties.name}: ${formatValue(v?.value ?? null, unit)}`}</title>
            </path>
          );
        })}
        {selectedFeature && (
          <path d={path(selectedFeature) ?? undefined} className="county-selected" />
        )}
      </svg>
      <figcaption>
        <ul className="legend" aria-label="Legend">
          {[...breaks, Infinity].map((b, i) => {
            const lo = i === 0 ? null : breaks[i - 1]!;
            const label = lo === null ? `< ${compact(b)}`
              : b === Infinity ? `≥ ${compact(lo)}` : `${compact(lo)}–${compact(b)}`;
            return <li key={i}><span className={`swatch c${i}`} />{label}</li>;
          })}
          <li><span className="swatch unknown-swatch" />no figure</li>
        </ul>
        <span className="muted">Quantile classes of the stated values ({unit}).</span>
      </figcaption>
    </figure>
  );
}
