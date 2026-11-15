import type { ReactNode } from "react";
import type { PlaceholderInfo, PreviewParagraph, PreviewSegment, TemplatePreview } from "@/lib/types";

// Renders the structured preview of a template's Word document. Everything is plain React
// text: the document's content never reaches the page as HTML.

function Segment({ segment, known }: { segment: PreviewSegment; known: Map<string, boolean> }) {
  if (segment.key !== null) {
    const ok = known.get(segment.key) ?? false;
    return (
      <span
        title={ok ? "Will be filled from the extraction" : "No field with this key: it will stay as it is"}
        className={`rounded px-1 font-mono text-[0.85em] ring-1 ring-inset ${
          ok ? "bg-ok-wash text-ok ring-ok/25" : "bg-red-50 text-bad ring-red-600/30"
        }`}
      >
        {segment.text}
      </span>
    );
  }
  let node: ReactNode = segment.text;
  if (segment.bold) node = <strong>{node}</strong>;
  if (segment.italic) node = <em>{node}</em>;
  if (segment.underline) node = <u>{node}</u>;
  return <>{node}</>;
}

function Paragraph({ paragraph, known }: { paragraph: PreviewParagraph; known: Map<string, boolean> }) {
  const content = paragraph.segments.map((segment, i) => <Segment key={i} segment={segment} known={known} />);
  // An empty paragraph is a spacer in Word; keep a little height for it.
  const empty = paragraph.segments.length === 0;
  if (empty) return <div className="h-3" />;
  switch (paragraph.style) {
    case "title":
      return <p className="mb-3 text-2xl font-bold text-ink">{content}</p>;
    case "heading": {
      const size = paragraph.level <= 1 ? "text-xl" : paragraph.level === 2 ? "text-lg" : "text-base";
      return <p className={`mt-4 mb-2 font-semibold text-ink ${size}`}>{content}</p>;
    }
    case "list":
      return (
        <p className="my-1 flex gap-2 pl-4">
          <span aria-hidden>•</span>
          <span>{content}</span>
        </p>
      );
    default:
      return <p className="my-1.5">{content}</p>;
  }
}

export function PlaceholderChips({ placeholders }: { placeholders: PlaceholderInfo[] }) {
  // The same key can appear many times in a document; list it once.
  const unique = placeholders.filter((p, i) => placeholders.findIndex((q) => q.key === p.key) === i);
  return (
    <div className="flex flex-wrap gap-2">
      {unique.map((p) => (
        <span
          key={p.key}
          className={`rounded px-2 py-1 font-mono text-xs ring-1 ring-inset ${
            p.known ? "bg-ok-wash text-ok ring-ok/25" : "bg-red-50 text-bad ring-red-600/30"
          }`}
        >
          {`{{${p.key}}}`}
        </span>
      ))}
    </div>
  );
}

export function TemplatePreviewView({ preview }: { preview: TemplatePreview }) {
  const known = new Map(preview.placeholders.map((p) => [p.key, p.known]));
  return (
    <div className="rounded-md bg-white p-10 font-serif text-[15px] leading-relaxed text-ink ring-1 ring-rule">
      {preview.blocks.length === 0 && <p className="text-ink-soft">The document is empty.</p>}
      {preview.blocks.map((block, i) =>
        block.type === "paragraph" ? (
          <Paragraph key={i} paragraph={block} known={known} />
        ) : (
          <table key={i} className="my-3 w-full border-collapse text-left">
            <tbody>
              {block.rows.map((row, r) => (
                <tr key={r}>
                  {row.map((cell, c) => (
                    <td key={c} className="border border-rule px-2 py-1 align-top">
                      {cell.map((paragraph, p) => (
                        <Paragraph key={p} paragraph={paragraph} known={known} />
                      ))}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        ),
      )}
      {preview.truncated && (
        <p className="mt-4 rounded bg-warn-wash px-3 py-2 text-warn">
          The preview shows only the beginning of a long document. The whole file is still used for filling.
        </p>
      )}
    </div>
  );
}
