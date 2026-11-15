import type { JSONContent } from "@tiptap/core";
import type { PreviewParagraph, PreviewSegment, PreviewTable } from "./types";

// The backend describes a document as blocks (paragraph, table). The editor works on a
// ProseMirror tree. These two functions translate between them, and nothing else in the app
// needs to know about both shapes.

type Block = PreviewParagraph | PreviewTable;

const PLACEHOLDER = /\{\{\s*([a-z][a-z0-9_]{0,63})\s*\}\}/g;

// ---------- blocks -> editor ----------

function marksOf(segment: PreviewSegment) {
  const marks: { type: string }[] = [];
  if (segment.bold) marks.push({ type: "bold" });
  if (segment.italic) marks.push({ type: "italic" });
  if (segment.underline) marks.push({ type: "underline" });
  return marks.length ? marks : undefined;
}

function inline(segment: PreviewSegment): JSONContent[] {
  const marks = marksOf(segment);
  if (segment.key !== null) return [{ type: "placeholder", attrs: { key: segment.key }, marks }];
  // A line break inside a run is a hard break in the editor.
  return segment.text
    .split("\n")
    .flatMap((line, i): JSONContent[] => [
      ...(i > 0 ? [{ type: "hardBreak" }] : []),
      ...(line ? [{ type: "text", text: line, marks }] : []),
    ]);
}

function paragraphNode(block: PreviewParagraph): JSONContent {
  const content = block.segments.flatMap(inline);
  const base: JSONContent = content.length ? { content } : {};
  if (block.style === "heading") return { type: "heading", attrs: { level: Math.min(block.level, 4) }, ...base };
  if (block.style === "title") return { type: "paragraph", attrs: { title: true }, ...base };
  return { type: "paragraph", ...base };
}

// Consecutive list paragraphs become one bullet list.
function nodes(paragraphs: PreviewParagraph[]): JSONContent[] {
  const result: JSONContent[] = [];
  for (const paragraph of paragraphs) {
    if (paragraph.style === "list") {
      const item: JSONContent = { type: "listItem", content: [paragraphNode({ ...paragraph, style: "normal" })] };
      const last = result[result.length - 1];
      if (last?.type === "bulletList") last.content!.push(item);
      else result.push({ type: "bulletList", content: [item] });
    } else {
      result.push(paragraphNode(paragraph));
    }
  }
  return result;
}

function tableNode(table: PreviewTable): JSONContent {
  return {
    type: "table",
    content: table.rows.map((row) => ({
      type: "tableRow",
      content: row.map((cell) => ({
        type: "tableCell",
        content: cell.length ? nodes(cell) : [{ type: "paragraph" }],
      })),
    })),
  };
}

export function blocksToEditor(blocks: Block[]): JSONContent {
  const content: JSONContent[] = [];
  let pending: PreviewParagraph[] = [];
  const flush = () => {
    content.push(...nodes(pending));
    pending = [];
  };
  for (const block of blocks) {
    if (block.type === "table") {
      flush();
      content.push(tableNode(block));
    } else {
      pending.push(block);
    }
  }
  flush();
  // An editor document must not be empty.
  return { type: "doc", content: content.length ? content : [{ type: "paragraph" }] };
}

// ---------- editor -> blocks ----------

function segmentsOf(node: JSONContent): PreviewSegment[] {
  const segments: PreviewSegment[] = [];
  const push = (text: string, key: string | null, marks: { type: string }[] | undefined) => {
    const has = (name: string) => !!marks?.some((m) => m.type === name);
    const next: PreviewSegment = { text, key, bold: has("bold"), italic: has("italic"), underline: has("underline") };
    const last = segments[segments.length - 1];
    // Neighbouring text with the same formatting is one run.
    if (key === null && last && last.key === null && last.bold === next.bold && last.italic === next.italic && last.underline === next.underline) {
      last.text += text;
    } else {
      segments.push(next);
    }
  };
  for (const child of node.content ?? []) {
    if (child.type === "text") push(child.text ?? "", null, child.marks);
    else if (child.type === "hardBreak") push("\n", null, undefined);
    else if (child.type === "placeholder") push(`{{${child.attrs?.key}}}`, String(child.attrs?.key), child.marks);
  }
  return segments;
}

function paragraphsOf(node: JSONContent, inList = false): PreviewParagraph[] {
  switch (node.type) {
    case "heading":
      return [{ type: "paragraph", style: "heading", level: Number(node.attrs?.level ?? 1), segments: segmentsOf(node) }];
    case "paragraph":
      return [
        {
          type: "paragraph",
          style: inList ? "list" : node.attrs?.title ? "title" : "normal",
          level: 1,
          segments: segmentsOf(node),
        },
      ];
    case "bulletList":
    case "orderedList":
      return (node.content ?? []).flatMap((item) => (item.content ?? []).flatMap((child) => paragraphsOf(child, true)));
    default:
      return [];
  }
}

export function editorToBlocks(doc: JSONContent): Block[] {
  const blocks: Block[] = [];
  for (const node of doc.content ?? []) {
    if (node.type === "table") {
      blocks.push({
        type: "table",
        rows: (node.content ?? []).map((row) =>
          (row.content ?? []).map((cell) => (cell.content ?? []).flatMap((child) => paragraphsOf(child))),
        ),
      });
    } else {
      blocks.push(...paragraphsOf(node));
    }
  }
  return blocks;
}

// ---------- helpers for the editor UI ----------

// Text with {{keys}} -> editor nodes (placeholders become real placeholder nodes).
export function textToNodes(text: string, marks?: { type: string }[]): JSONContent[] {
  const nodes: JSONContent[] = [];
  const lines = text.split("\n");
  lines.forEach((line, lineIndex) => {
    if (lineIndex > 0) nodes.push({ type: "hardBreak" });
    let position = 0;
    for (const match of line.matchAll(PLACEHOLDER)) {
      if (match.index > position) nodes.push({ type: "text", text: line.slice(position, match.index), marks });
      nodes.push({ type: "placeholder", attrs: { key: match[1] }, marks });
      position = match.index + match[0].length;
    }
    if (position < line.length) nodes.push({ type: "text", text: line.slice(position), marks });
  });
  return nodes;
}

// How many times each key is used, in document order of first use.
export function placeholderCounts(doc: JSONContent): Map<string, number> {
  const counts = new Map<string, number>();
  const walk = (node: JSONContent) => {
    if (node.type === "placeholder") {
      const key = String(node.attrs?.key);
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    node.content?.forEach(walk);
  };
  walk(doc);
  return counts;
}
