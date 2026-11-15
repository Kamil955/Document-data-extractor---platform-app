import { describe, expect, it } from "vitest";
import { locateQuote } from "./locate-quote";

const page = [
  "6.2 Governing Law. This Agreement shall be governed by the laws of the",
  "State of Washington, without regard to conflict of law principles.",
  "7. Notices. Either party may terminate on ten (10) business days written",
  "notice.",
];

describe("locateQuote", () => {
  it("finds a quote inside one text item", () => {
    const found = locateQuote(page, "without regard to conflict of law principles");
    expect(found?.exact).toBe(true);
    expect(found?.ranges.map((r) => r.item)).toEqual([1]);
    const { start, end } = found!.ranges[0];
    expect(page[1].slice(start, end)).toBe("without regard to conflict of law principles");
  });

  it("finds a quote that runs over a line break", () => {
    const found = locateQuote(page, "the laws of the State of Washington");
    expect(found?.exact).toBe(true);
    expect(found?.ranges.map((r) => r.item)).toEqual([0, 1]);
  });

  it("covers a word that the quote only reaches into", () => {
    // The quote ends after "Wash": the highlight must still include the whole word.
    const found = locateQuote(["governed by the State of Washington, without"], "the State of Wash");
    const { start, end } = found!.ranges[0];
    expect("governed by the State of Washington, without".slice(start, end)).toBe("the State of Washington");
  });

  it("ignores case, punctuation, spacing and line-end hyphens", () => {
    const items = ["The Supplier shall deliver the agree-", "ment within thirty (30) days."];
    const found = locateQuote(items, "deliver the AGREEMENT  within thirty 30 days");
    expect(found?.exact).toBe(true);
  });

  it("matches ligatures and curly quotes", () => {
    const items = ["The ﬁnal “Effective Date” is"];
    expect(locateQuote(items, 'The final "Effective Date" is')?.exact).toBe(true);
  });

  it("falls back to the beginning of a quote that continues on the next page", () => {
    const items = ["Either party may terminate this agreement on ten (10) business"];
    const quote = "Either party may terminate this agreement on ten (10) business days written notice to the other party";
    const found = locateQuote(items, quote);
    expect(found?.exact).toBe(false);
    expect(found?.ranges.map((r) => r.item)).toEqual([0]);
  });

  it("falls back to the end of a quote that started on the previous page", () => {
    const items = ["days written notice to the other party and no other formality is needed."];
    const quote = "Either party may terminate this agreement on ten (10) business days written notice to the other party";
    expect(locateQuote(items, quote)?.exact).toBe(false);
  });

  it("does not highlight anything for a quote that is not on the page", () => {
    expect(locateQuote(page, "Confidential Information shall not include public data")).toBeNull();
  });

  it("does not match a short fragment by accident", () => {
    // Too short for a partial match, and not present as a whole.
    expect(locateQuote(page, "the laws of Utah")).toBeNull();
  });

  it("copes with an empty quote and an empty page", () => {
    expect(locateQuote(page, "  ... ")).toBeNull();
    expect(locateQuote([], "anything here")).toBeNull();
  });
});
