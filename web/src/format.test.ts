import { classOf, formatValue, quantileBreaks } from "./format";

test("values keep their unit and are never invented", () => {
  expect(formatValue(1234567.4, "acre-feet")).toBe("1,234,567 acre-feet");
  expect(formatValue(41.26, "percent")).toBe("41.3%");
  expect(formatValue(192, "feet")).toBe("192 ft");
  expect(formatValue(null, "acre-feet")).toBe("no figure");
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
