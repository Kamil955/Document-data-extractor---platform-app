"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { type FieldState, fieldState } from "@/lib/field-state";
import type { Citation, Extraction, FieldResult } from "@/lib/types";
import { FieldCard } from "./field-card";
import { FillPanel } from "./fill-panel";
import { SourceViewer } from "./source-viewer";
import { ErrorBox, PageHeader, ProgressBar, Spinner } from "./ui";

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

  return (
    <>
      <PageHeader title="Review extracted data">
        <Link href={`/documents/${extraction.document_id}`} className="text-sm text-zinc-600 hover:text-zinc-900">
          ← Run again
        </Link>
      </PageHeader>

      {working && (
        <div className="mb-5 rounded-lg bg-white p-4 shadow-sm ring-1 ring-zinc-200">
          <p className="mb-2 text-sm text-zinc-700">
            {extraction.status === "pending"
              ? "Waiting for the worker to start…"
              : `Reading the document: ${extraction.results.length} of ${extraction.total} fields done.`}
          </p>
          <ProgressBar done={extraction.results.length} total={extraction.total} />
          <p className="mt-2 text-xs text-zinc-500">
            You can leave this page: the extraction continues and is listed on the document.
          </p>
        </div>
      )}

      {extraction.status === "failed" && (
        <div className="mb-5">
          <ErrorBox>
            The extraction failed after {extraction.results.length} of {extraction.total} fields:{" "}
            {extraction.error ?? "unknown error"}
          </ErrorBox>
        </div>
      )}

      <p className="mb-4 text-sm text-zinc-600">
        {count((s) => s === "verified" || s === "edited")} of {extraction.total} fields are verified or confirmed.
        {count((s) => s === "check" || s === "error") > 0 && (
          <strong className="ml-1 text-amber-800">{count((s) => s === "check" || s === "error")} need your check.</strong>
        )}
        <span className="ml-2 text-zinc-400">Model: {extraction.model}</span>
      </p>

      <div className="mb-5 flex gap-2" role="tablist">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            role="tab"
            aria-selected={filter === f.id}
            onClick={() => setFilter(f.id)}
            className={`rounded-full px-3 py-1 text-sm ring-1 ring-inset ${
              filter === f.id ? "bg-zinc-900 text-white ring-zinc-900" : "bg-white text-zinc-700 ring-zinc-300 hover:bg-zinc-50"
            }`}
          >
            {f.label} ({count(f.match)})
          </button>
        ))}
      </div>

      <ul className="space-y-3">
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
