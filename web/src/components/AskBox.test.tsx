import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AskBox } from "./AskBox";

const answer = {
  question: "temperature and rainfall in Bexar County 2021",
  status: "partial",
  statements: [{
    county: "Bexar", fips: "48029", year: 2021, metric: "avg_temp", label: "Average temperature",
    value: 69.4, unit: "degF", citation: "375d36df6946:L120",
    text: "Average temperature, Bexar County, 2021: 69.4 °F",
  }],
  missing: ["Precipitation, Bexar County, 2021 (left blank by the source)"],
  reason: null,
  notes: [],
  synthetic: true,
  log_id: "abc123",
};

const source = {
  citation: "375d36df6946:L120", dataset: "county_climate", title: "Annual climate by county",
  publisher: "Publisher", source_url: "synthetic://x", captured_at: "2026-11-05T06:00:00+00:00",
  sha256: "375d36df6946" + "0".repeat(52), line: 120, synthetic: true,
  derived_from: null, method: null,
  row: { County: "Bexar County", Year: "2021", "Average Temperature (F)": "69.4", "Precipitation (in)": "" },
};

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({
    ok: true,
    json: async () => (String(url).startsWith("api/citations") ? source : answer),
  })));
});

test("shows a partial answer with what is missing, and opens a citation", async () => {
  const user = userEvent.setup();
  render(<AskBox />);
  await user.type(screen.getByLabelText("Question"), "temperature and rainfall in Bexar County 2021");
  await user.click(screen.getByRole("button", { name: "Ask" }));

  expect(await screen.findByText("Partly answered")).toBeInTheDocument();
  expect(screen.getByText(/69.4 °F/)).toBeInTheDocument();
  expect(screen.getByText(/left blank by the source/)).toBeInTheDocument();
  expect(screen.getByText("synthetic sample")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "375d36df6946:L120" }));
  const region = await screen.findByRole("region", { name: /Source for/ });
  expect(region).toHaveTextContent("Bexar County");
  expect(region).toHaveTextContent("blank");   // an empty source cell is shown as blank
  expect(region).toHaveTextContent(/sha256 375d36df6946/);
});

test("a declined question shows the reason", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({
    ok: true,
    json: async () => ({ ...answer, status: "declined", statements: [], missing: [], notes: [],
      reason: "forecast: The platform reports recorded figures only. It doesn't forecast." }),
  })));
  const user = userEvent.setup();
  render(<AskBox />);
  await user.click(screen.getByRole("button", { name: /Will it rain/ }));
  expect(await screen.findByText("Out of scope")).toBeInTheDocument();
  expect(screen.getByText(/doesn't forecast/)).toBeInTheDocument();
});
