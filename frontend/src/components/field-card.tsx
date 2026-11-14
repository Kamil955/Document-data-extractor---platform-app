"use client";

import { useState } from "react";
import { ApiError, api } from "@/lib/api";
import { STATE_LABEL, STATE_STYLE, fieldState } from "@/lib/field-state";
import type { Citation, FieldResult } from "@/lib/types";
import { Badge, ErrorBox, buttonClass, inputClass, secondaryButtonClass } from "./ui";

function pageLabel(citation: Citation): string | null {
  if (citation.page_start === null) return null;
  return citation.page_end && citation.page_end !== citation.page_start
    ? `pp. ${citation.page_start}–${citation.page_end}`
    : `p. ${citation.page_start}`;
}

function CitationView({ citation }: { citation: Citation }) {
  const where = [pageLabel(citation), citation.section_path].filter(Boolean).join(" · ");
  return (
    <blockquote
      className={`rounded-md border-l-4 px-3 py-2 text-sm ${
        citation.verified ? "border-emerald-500 bg-emerald-50/60" : "border-amber-500 bg-amber-50"
      }`}
    >
      <p className="text-zinc-800">“{citation.quote}”</p>
      <p className="mt-1 text-xs text-zinc-500">
        {where || "location unknown"}
        {!citation.verified && (
          <span className="ml-2 font-medium text-amber-800">
            This quote was not found word for word in the source: do not rely on it.
          </span>
        )}
      </p>
    </blockquote>
  );
}

export function FieldCard({
  extractionId,
  field,
  onSaved,
}: {
  extractionId: string;
  field: FieldResult;
  onSaved: (field: FieldResult) => void;
}) {
  const [draft, setDraft] = useState(field.value);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const state = fieldState(field);
  const dirty = draft.trim() !== field.value.trim();

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const saved = await api.correctValue(extractionId, field.key, draft);
      setDraft(saved.value);
      onSaved(saved);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Saving failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <li className="rounded-lg bg-white p-4 shadow-sm ring-1 ring-zinc-200">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-medium text-zinc-900">{field.label}</p>
          <p className="font-mono text-xs text-zinc-400">{`{{${field.key}}}`}</p>
        </div>
        <Badge className={STATE_STYLE[state]}>{STATE_LABEL[state]}</Badge>
      </div>

      <textarea
        className={`${inputClass} min-h-[2.5rem] resize-y`}
        rows={field.value.length > 90 ? 3 : 1}
        value={draft}
        placeholder={state === "missing" ? "Not found in the document. Type a value if you know it." : ""}
        onChange={(e) => setDraft(e.target.value)}
        aria-label={field.label}
      />

      {(dirty || state === "check") && (
        <div className="mt-2 flex gap-2">
          {dirty ? (
            <>
              <button className={buttonClass} disabled={saving} onClick={() => void save()}>
                Save value
              </button>
              <button className={secondaryButtonClass} disabled={saving} onClick={() => setDraft(field.value)}>
                Undo
              </button>
            </>
          ) : (
            <button className={buttonClass} disabled={saving} onClick={() => void save()}>
              Confirm value
            </button>
          )}
        </div>
      )}

      {state === "check" && (
        <p className="mt-2 text-xs text-amber-800">
          The model found a value but no quote that proves it. Check it against the document, then confirm.
        </p>
      )}
      {field.error && <p className="mt-2 text-xs text-red-700">{field.error}</p>}
      {error && (
        <div className="mt-2">
          <ErrorBox>{error}</ErrorBox>
        </div>
      )}

      {field.citations.length > 0 && (
        <div className="mt-3 space-y-2">
          {field.citations.map((citation, i) => (
            <CitationView key={i} citation={citation} />
          ))}
        </div>
      )}
    </li>
  );
}
