import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AskBox } from "./AskBox";

const answer = {
  question: "water use in Bexar County 2021",
  status: "partial",
  statements: [{
    county: "Bexar", fips: "48029", year: 2021, metric: "municipal", label: "Municipal use",
    value: 210000, unit: "acre-feet", citation: "375d36df6946:L120",
    text: "Municipal use, Bexar County, 2021: 210,000 acre-feet",
  }],
  missing: ["Mining use, Bexar County, 2021 (left blank by the source)"],
  reason: null,
  notes: ["Water use is reported by category."],
  synthetic: true,
  log_id: "abc123",
};

const source = {
  citation: "375d36df6946:L120", dataset: "water_use", title: "Water use by county",
  publisher: "Publisher", source_url: "synthetic://x", captured_at: "2026-11-05T06:00:00+00:00",
  sha256: "375d36df6946" + "0".repeat(52), line: 120, synthetic: true,
  row: { County: "BEXAR", Year: "2021", Municipal: "210,000", Mining: "" },
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
  await user.type(screen.getByLabelText("Question"), "water use in Bexar County 2021");
  await user.click(screen.getByRole("button", { name: "Ask" }));

  expect(await screen.findByText("Partly answered")).toBeInTheDocument();
  expect(screen.getByText(/210,000 acre-feet/)).toBeInTheDocument();
  expect(screen.getByText(/left blank by the source/)).toBeInTheDocument();
  expect(screen.getByText("synthetic sample")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "375d36df6946:L120" }));
  const region = await screen.findByRole("region", { name: /Source for/ });
  expect(region).toHaveTextContent("BEXAR");
  expect(region).toHaveTextContent("blank");   // an empty source cell is shown as blank
  expect(region).toHaveTextContent(/sha256 375d36df6946/);
});

test("a declined question shows the reason", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({
    ok: true,
    json: async () => ({ ...answer, status: "declined", statements: [], missing: [], notes: [],
      reason: "cause: The platform reports what sources state. It doesn't explain causes." }),
  })));
  const user = userEvent.setup();
  render(<AskBox />);
  await user.click(screen.getByRole("button", { name: /Why did irrigation fall/ }));
  expect(await screen.findByText("Out of scope")).toBeInTheDocument();
  expect(screen.getByText(/doesn't explain causes/)).toBeInTheDocument();
});
