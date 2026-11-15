import { describe, expect, it } from "vitest";
import { blocksToEditor, editorToBlocks, placeholderCounts, textToNodes } from "./editor-model";
import type { PreviewParagraph, PreviewTable } from "./types";

const seg = (text: string, extra: Partial<PreviewParagraph["segments"][number]> = {}) => ({
  text,
  key: null,
  bold: false,
  italic: false,
  underline: false,
  ...extra,
});
const para = (style: PreviewParagraph["style"], segments: PreviewParagraph["segments"], level = 1): PreviewParagraph => ({
  type: "paragraph",
  style,
  level,
  segments,
});

describe("editor model", () => {
  it("round-trips paragraphs, headings, lists, tables and placeholders", () => {
    const table: PreviewTable = {
      type: "table",
      rows: [[[para("normal", [seg("Term")])], [para("normal", [seg("{{term}}", { key: "term", bold: true })])]]],
    };
    const blocks = [
      para("title", [seg("Summary")]),
      para("heading", [seg("Key terms")], 2),
      para("normal", [seg("Law: "), seg("{{governing_law}}", { key: "governing_law" }), seg(" applies", { italic: true, underline: true })]),
      para("list", [seg("one")]),
      para("list", [seg("two")]),
      table,
      para("normal", []),
    ];

    expect(editorToBlocks(blocksToEditor(blocks))).toEqual(blocks);
  });

  it("groups consecutive list paragraphs into one bullet list", () => {
    const doc = blocksToEditor([para("list", [seg("a")]), para("list", [seg("b")])]);

    expect(doc.content).toHaveLength(1);
    expect(doc.content![0].type).toBe("bulletList");
    expect(doc.content![0].content).toHaveLength(2);
  });

  it("keeps line breaks inside a paragraph", () => {
    const blocks = [para("normal", [seg("a\nb")])];

    expect(editorToBlocks(blocksToEditor(blocks))).toEqual(blocks);
  });

  it("never gives the editor an empty document", () => {
    expect(blocksToEditor([]).content).toEqual([{ type: "paragraph" }]);
  });

  it("merges neighbouring text with the same formatting", () => {
    const blocks = editorToBlocks({
      type: "doc",
      content: [{ type: "paragraph", content: [{ type: "text", text: "a" }, { type: "text", text: "b" }] }],
    });

    expect(blocks).toEqual([para("normal", [seg("ab")])]);
  });

  it("turns {{keys}} in plain text into placeholder nodes", () => {
    const nodes = textToNodes("Law: {{governing_law}}.\nNext {{ term }}");

    expect(nodes.map((n) => n.type)).toEqual(["text", "placeholder", "text", "hardBreak", "text", "placeholder"]);
    expect(nodes[1].attrs).toEqual({ key: "governing_law" });
    expect(nodes[5].attrs).toEqual({ key: "term" });
  });

  it("counts placeholders, also inside tables and lists", () => {
    const doc = blocksToEditor([
      para("normal", [seg("{{a}}", { key: "a" })]),
      para("list", [seg("{{a}}", { key: "a" }), seg("{{b}}", { key: "b" })]),
    ]);

    expect([...placeholderCounts(doc)]).toEqual([
      ["a", 2],
      ["b", 1],
    ]);
  });
});
