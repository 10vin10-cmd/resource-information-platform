// Writes the Texas county list (FIPS, name, centroid) from the US Census
// cartographic boundaries packaged in us-atlas, and a Texas-only TopoJSON for
// the map. Run once; both outputs are committed.
import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { geoCentroid } from "d3-geo";
import { feature } from "topojson-client";

const require = createRequire(import.meta.url);
const us = JSON.parse(readFileSync(require.resolve("us-atlas/counties-10m.json"), "utf8"));
const TX = "48";

const counties = feature(us, us.objects.counties).features
  .filter((f) => String(f.id).startsWith(TX))
  .sort((a, b) => String(a.id).localeCompare(String(b.id)));

const rows = ["fips,name,lon,lat"];
for (const f of counties) {
  const [lon, lat] = geoCentroid(f);
  rows.push(`${f.id},${f.properties.name},${lon.toFixed(4)},${lat.toFixed(4)}`);
}
writeFileSync(new URL("../../resource_platform/data/texas_counties.csv", import.meta.url), rows.join("\n") + "\n");

// Keep only Texas county geometries in the topology the app loads.
const geoms = us.objects.counties.geometries.filter((g) => String(g.id).startsWith(TX));
const topo = { ...us, objects: { counties: { type: "GeometryCollection", geometries: geoms } } };
delete topo.objects.states;
delete topo.objects.nation;
writeFileSync(new URL("../public/texas-counties.json", import.meta.url), JSON.stringify(topo));
console.log(`${counties.length} counties`);
