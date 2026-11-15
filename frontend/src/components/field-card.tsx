"use client";

import { useState } from "react";
import { ApiError, api } from "@/lib/api";
import { STATE_LABEL, STATE_TONE, fieldState } from "@/lib/field-state";
import type { Citation, FieldResult } from "@/lib/types";
import { Badge, ErrorBox, buttonClass, inputClass, secondaryButtonClass } from "./ui";

function pageLabel(citation: Citation): string | null {
  if (citation.page_start === null) return null;
  return citation.page_end && citation.page_end !== citation.page_start
    ? `pp. ${citation.page_start}–${citation.page_end}`
    : `p. ${citation.page_start}`;
}

// A quote from the source, set in the typeface of a contract: this is the evidence behind a
// value. Teal rule = found word for word in the document; amber = it was not.
function CitationView({ citation, onShow }: { citation: Citation; onShow: (citation: Citation) => void }) {
  const where = [pageLabel(citation), citation.section_path].filter(Boolean).join(" · ");
  return (
    <blockquote className={`border-l-[3px] py-1 pl-4 ${citation.verified ? "border-ok" : "border-[#d98a1c]"}`}>
      <p className="font-serif text-[15px] leading-relaxed text-ink">“{citation.quote}”</p>
      <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-soft">
        <button className="font-medium text-accent underline-offset-2 hover:underline" onClick={() => onShow(citation)}>
          Show in document
        </button>
        <span>{where || "location unknown"}</span>
      </p>
      {!citation.verified && (
        <p className="mt-1.5 text-xs font-medium text-warn">
          This quote was not found word for word in the source. Do not rely on it.
        </p>
      )}
    </blockquote>
  );
}

export function FieldCard({
  extractionId,
  field,
  onSaved,
  onShowSource,
  locked,
}: {
  extractionId: string;
  field: FieldResult;
  onSaved: (field: FieldResult) => void;
  onShowSource: (citation: Citation) => void;
  // True while the worker is still running: the API refuses changes then (409).
  locked: boolean;
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
    <li className="grid gap-x-10 gap-y-4 px-6 py-6 md:grid-cols-[13rem_1fr]">
      <div>
        <p className="font-medium text-ink">{field.label}</p>
        <p className="mt-0.5 font-mono text-xs text-ink-faint">{`{{${field.key}}}`}</p>
        <div className="mt-3">
          <Badge tone={STATE_TONE[state]}>{STATE_LABEL[state]}</Badge>
        </div>
      </div>

      <div className="min-w-0">
        <textarea
          className={`${inputClass} min-h-[2.5rem] resize-y`}
          rows={field.value.length > 90 ? 3 : 1}
          value={draft}
          placeholder={state === "missing" ? "Not found in the document. Type a value if you know it." : ""}
          onChange={(e) => setDraft(e.target.value)}
          readOnly={locked}
          aria-label={field.label}
        />

        {!locked && (dirty || state === "check") && (
          <div className="mt-3 flex items-center gap-2">
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
          <p className="mt-3 text-sm text-warn">
            The model found a value but no quote that proves it. Check it against the document, then confirm.
          </p>
        )}
        {field.error && <p className="mt-3 text-sm text-bad">{field.error}</p>}
        {error && (
          <div className="mt-3">
            <ErrorBox>{error}</ErrorBox>
          </div>
        )}

        {field.citations.length > 0 && (
          <div className="mt-5 space-y-4">
            {field.citations.map((citation, i) => (
              <CitationView key={i} citation={citation} onShow={onShowSource} />
            ))}
          </div>
        )}
      </div>
    </li>
  );
}
