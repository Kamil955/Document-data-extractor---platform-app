"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import type { ExtractionStatus, ExtractionSummary } from "@/lib/types";
import { Badge, ErrorBox } from "./ui";

const STATUS_STYLE: Record<ExtractionStatus, { label: string; className: string }> = {
  pending: { label: "Waiting", className: "bg-zinc-100 text-zinc-700 ring-zinc-300" },
  running: { label: "Running", className: "bg-blue-50 text-blue-800 ring-blue-600/20" },
  completed: { label: "Done", className: "bg-emerald-50 text-emerald-800 ring-emerald-600/20" },
  failed: { label: "Failed", className: "bg-red-50 text-red-800 ring-red-600/20" },
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
      <h2 className="mb-3 text-sm font-semibold text-zinc-900">Previous extractions</h2>
      <ul className="divide-y divide-zinc-200 rounded-lg bg-white shadow-sm ring-1 ring-zinc-200">
        {items.map((item) => {
          const style = STATUS_STYLE[item.status];
          return (
            <li key={item.extraction_id}>
              <Link
                href={`/extractions/${item.extraction_id}`}
                className="flex items-center justify-between gap-4 px-4 py-3 text-sm hover:bg-zinc-50"
              >
                <span>
                  <span className="font-medium text-zinc-900">{item.template_name ?? "Custom fields"}</span>
                  <span className="ml-2 text-zinc-400">{new Date(item.created_at).toLocaleString()}</span>
                </span>
                <span className="flex items-center gap-3">
                  <span className="text-zinc-500">
                    {item.done}/{item.total} fields
                  </span>
                  <Badge className={style.className}>{style.label}</Badge>
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
