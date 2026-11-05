import { classOf, formatValue, quantileBreaks } from "./format";

test("values keep their unit and are never invented", () => {
  expect(formatValue(68.94, "degF")).toBe("68.9 °F");
  expect(formatValue(31.4, "inches")).toBe("31.40 in");
  expect(formatValue(1234567.4, "USD")).toBe("$1,234,567");
  expect(formatValue(1, "events")).toBe("1 event");
  expect(formatValue(0, "events")).toBe("0 events");
  expect(formatValue(null, "inches")).toBe("no figure");
});

test("quantile classes ignore unknowns and handle ties", () => {
  const breaks = quantileBreaks([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  expect(breaks).toEqual([3, 5, 7, 9]);
  expect(classOf(1, breaks)).toBe(0);
  expect(classOf(10, breaks)).toBe(4);
  expect(classOf(null, breaks)).toBe(-1);
  expect(quantileBreaks([5, 5, 5, 5])).toEqual([5]);
  expect(quantileBreaks([])).toEqual([]);
});
