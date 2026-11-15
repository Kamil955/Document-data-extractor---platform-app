import type { TemplateField } from "@/lib/types";
import { PlusIcon } from "./icons";

// Left rail: the template's fields. A click puts the placeholder at the cursor, so nobody has
// to remember the exact {{key}}. The count shows which fields the document already uses.
export function FieldsPanel({
  fields,
  counts,
  onInsert,
}: {
  fields: TemplateField[];
  counts: Map<string, number>;
  onInsert: (key: string) => void;
}) {
  const known = new Set(fields.map((f) => f.key));
  const stray = [...counts.keys()].filter((key) => !known.has(key));

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-[var(--rule)] bg-white">
      <div className="px-5 pt-5 pb-3">
        <h2 className="text-sm font-semibold text-[var(--ink)]">Fields</h2>
        <p className="mt-1 text-xs leading-relaxed text-[var(--ink-soft)]">Click a field to insert it where the cursor is. To reword text, select it inside one paragraph and choose Ask AI.</p>
      </div>

      <ul className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {fields.map((field) => {
          const used = counts.get(field.key) ?? 0;
          return (
            <li key={field.key}>
              <button
                type="button"
                // Keep the cursor in the document: a button press must not steal the focus.
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => onInsert(field.key)}
                title={field.description ?? `Insert {{${field.key}}}`}
                className="group flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition hover:bg-[#eef0f8] focus-visible:outline-2 focus-visible:outline-[var(--accent)]"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-[var(--ink)]">{field.label}</span>
                  <span className="block truncate font-mono text-[11px] text-[var(--ink-soft)]">{field.key}</span>
                </span>
                {used > 0 ? (
                  <span className="rounded-full bg-[var(--ph-bg)] px-2 py-0.5 text-xs font-medium text-[var(--ph-ink)]" title={`Used ${used} time${used > 1 ? "s" : ""}`}>
                    {used}×
                  </span>
                ) : (
                  <span className="text-xs text-[var(--ink-soft)] group-hover:hidden">not used</span>
                )}
                <span className="hidden text-[var(--accent)] group-hover:block">
                  <PlusIcon />
                </span>
              </button>
            </li>
          );
        })}
        {fields.length === 0 && <li className="px-3 py-2 text-xs text-[var(--ink-soft)]">This template has no fields.</li>}
      </ul>

      {stray.length > 0 && (
        <div className="mx-4 mb-3 rounded-lg bg-[var(--bad-bg)] px-3 py-2.5 text-xs leading-relaxed text-[var(--bad-ink)]">
          <p className="font-medium">Not a field of this template</p>
          <p className="mt-0.5">{stray.map((key) => `{{${key}}}`).join(", ")} will stay as typed when you fill the document.</p>
        </div>
      )}

      <p className="border-t border-[var(--rule)] px-5 py-3 text-[11px] leading-relaxed text-[var(--ink-soft)]">
        Saving keeps your styles, headers and footers. Custom fonts, colours, alignment and images in the body are not kept.
      </p>
    </aside>
  );
}
