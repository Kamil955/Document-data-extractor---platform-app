"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { type FieldState, fieldState } from "@/lib/field-state";
import type { Citation, Extraction, FieldResult } from "@/lib/types";
import { FieldCard } from "./field-card";
import { FillPanel } from "./fill-panel";
import { SourceViewer } from "./source-viewer";
import { ErrorBox, PageHeader, ProgressBar, Spinner, surfaceClass } from "./ui";

type Filter = "all" | "review" | "missing";

const FILTERS: { id: Filter; label: string; match: (s: FieldState) => boolean }[] = [
  { id: "all", label: "All", match: () => true },
  { id: "review", label: "Needs check", match: (s) => s === "check" || s === "error" },
  { id: "missing", label: "Not found", match: (s) => s === "missing" },
];

export function ExtractionView() {
  const { id } = useParams<{ id: string }>();
  const [extraction, setExtraction] = useState<Extraction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  // The citation whose source is open in the side panel (null = closed).
  const [source, setSource] = useState<Citation | null>(null);

  useEffect(() => {
    api
      .getExtraction(id)
      .then(setExtraction)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Unexpected error"));
  }, [id]);

  // While the worker is busy, ask again every 2 seconds; finished fields show up one by one.
  // The effect re-runs when `working` flips to false, and then clears the timer.
  const working = extraction?.status === "pending" || extraction?.status === "running";
  useEffect(() => {
    if (!working) return;
    const timer = setInterval(() => {
      api
        .getExtraction(id)
        .then(setExtraction)
        .catch((e) => setError(e instanceof ApiError ? e.message : "Unexpected error"));
    }, 2000);
    return () => clearInterval(timer);
  }, [working, id]);

  function replace(saved: FieldResult) {
    setExtraction((current) =>
      current && {
        ...current,
        results: current.results.map((r) => (r.key === saved.key ? { ...saved, citations: r.citations } : r)),
      },
    );
  }

  if (error) return <ErrorBox>{error}</ErrorBox>;
  if (!extraction) return <Spinner label="Loading…" />;

  const states = extraction.results.map(fieldState);
  const count = (match: (s: FieldState) => boolean) => states.filter(match).length;
  const active = FILTERS.find((f) => f.id === filter) ?? FILTERS[0];

  const verified = count((s) => s === "verified");
  const confirmed = count((s) => s === "edited");
  const check = count((s) => s === "check" || s === "error");
  const missing = count((s) => s === "missing");
  const settled = verified + confirmed;
  // The segments of the summary bar, in the order a person reads them.
  const segments = [
    { label: "Verified", n: verified, bar: "bg-ok" },
    { label: "Confirmed by you", n: confirmed, bar: "bg-accent" },
    { label: "Needs check", n: check, bar: "bg-[#d98a1c]" },
    { label: "Not found", n: missing, bar: "bg-ink-faint/50" },
  ];

  return (
    <>
      <PageHeader
        title="Review extracted data"
        description="Check every value against the quote behind it. Confirm or correct it, then fill your Word template."
        back={{ href: `/documents/${extraction.document_id}`, label: "Document" }}
      />

      {working && (
        <div className={`mb-6 px-6 py-5 ${surfaceClass}`}>
          <p className="mb-3 text-sm text-ink">
            {extraction.status === "pending"
              ? "Waiting for the worker to start…"
              : `Reading the document: ${extraction.results.length} of ${extraction.total} fields done.`}
          </p>
          <ProgressBar done={extraction.results.length} total={extraction.total} />
          <p className="mt-3 text-sm text-ink-soft">
            You can leave this page: the extraction continues and is listed on the document.
          </p>
        </div>
      )}

      {extraction.status === "failed" && (
        <div className="mb-6">
          <ErrorBox>
            The extraction failed after {extraction.results.length} of {extraction.total} fields:{" "}
            {extraction.error ?? "unknown error"}
          </ErrorBox>
        </div>
      )}

      <div className={`mb-6 px-6 py-5 ${surfaceClass}`}>
        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
          <p className="text-lg font-semibold tracking-[-0.01em] text-ink">
            {settled} of {extraction.total} fields verified or confirmed
          </p>
          <p className="text-xs text-ink-faint">Model: {extraction.model}</p>
        </div>
        <div className="mt-4 flex h-2 w-full gap-0.5 overflow-hidden rounded-full bg-rule" role="img" aria-label={segments.map((x) => `${x.n} ${x.label.toLowerCase()}`).join(", ")}>
          {segments.map((x) => x.n > 0 && <div key={x.label} className={x.bar} style={{ flexGrow: x.n }} />)}
        </div>
        <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-soft">
          {segments.map((x) => (
            <li key={x.label} className="flex items-center gap-1.5">
              <span className={`h-2 w-2 rounded-full ${x.bar}`} aria-hidden />
              {x.n} {x.label.toLowerCase()}
            </li>
          ))}
        </ul>
      </div>

      <div className="mb-4 inline-flex rounded-lg bg-white p-0.5 ring-1 ring-rule" role="tablist">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            role="tab"
            aria-selected={filter === f.id}
            onClick={() => setFilter(f.id)}
            className={`rounded-md px-3.5 py-1.5 text-sm transition ${
              filter === f.id ? "bg-ink font-medium text-white" : "text-ink-soft hover:text-ink"
            }`}
          >
            {f.label} <span className={filter === f.id ? "text-white/70" : "text-ink-faint"}>{count(f.match)}</span>
          </button>
        ))}
      </div>

      <ul className={`divide-y divide-rule ${surfaceClass}`}>
        {extraction.results
          .filter((field) => active.match(fieldState(field)))
          // key includes the saved value, so a card restarts its draft when the saved value changes.
          .map((field) => (
            <FieldCard key={`${field.key}:${field.value}:${field.edited}`} extractionId={extraction.extraction_id} field={field} onSaved={replace} onShowSource={setSource} locked={working} />
          ))}
      </ul>

      {!working && <FillPanel extractionId={extraction.extraction_id} templateId={extraction.template_id} />}

      <SourceViewer citation={source} onClose={() => setSource(null)} />
    </>
  );
}
