"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import type { ExtractionStatus, ExtractionSummary } from "@/lib/types";
import { formatDate } from "@/lib/format";
import { Badge, ErrorBox, type Tone, surfaceClass } from "./ui";

const STATUS: Record<ExtractionStatus, { label: string; tone: Tone }> = {
  pending: { label: "Waiting", tone: "neutral" },
  running: { label: "Running", tone: "info" },
  completed: { label: "Done", tone: "ok" },
  failed: { label: "Failed", tone: "bad" },
};

// Extractions run in the background, so a person can leave the page: this list is the way back.
export function ExtractionsList({ documentId }: { documentId: string }) {
  const [items, setItems] = useState<ExtractionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listExtractions(documentId)
      .then(setItems)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Unexpected error"));
  }, [documentId]);

  if (error) return <ErrorBox>{error}</ErrorBox>;
  if (!items || items.length === 0) return null;

  return (
    <section className="mt-8">
      <h2 className="mb-3 text-sm font-semibold text-ink">Previous extractions</h2>
      <ul className={`divide-y divide-rule ${surfaceClass}`}>
        {items.map((item) => {
          const status = STATUS[item.status];
          return (
            <li key={item.extraction_id}>
              <Link
                href={`/extractions/${item.extraction_id}`}
                className="flex items-center justify-between gap-4 px-5 py-3.5 text-sm transition first:rounded-t-xl last:rounded-b-xl hover:bg-wash"
              >
                <span>
                  <span className="font-medium text-ink">{item.template_name ?? "Custom fields"}</span>
                  <span className="ml-2 text-ink-soft">{formatDate(item.created_at)}</span>
                </span>
                <span className="flex items-center gap-3">
                  <span className="text-ink-soft">
                    {item.done}/{item.total} fields
                  </span>
                  <Badge tone={status.tone}>{status.label}</Badge>
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
