"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";
import type { DocumentItem, DocumentStatus } from "@/lib/types";
import { formatDate } from "@/lib/format";
import { Badge, EmptyState, ErrorBox, PageHeader, Spinner, type Tone, buttonClass, surfaceClass } from "./ui";

const STATUS_TONE: Record<DocumentStatus, Tone> = {
  uploaded: "neutral",
  processing: "info",
  indexed: "ok",
  failed: "bad",
};
const STATUS_LABEL: Record<DocumentStatus, string> = {
  uploaded: "Queued",
  processing: "Reading",
  indexed: "Ready",
  failed: "Failed",
};

// PDF or DOCX, as a small chip in front of the file name.
function FileChip({ name }: { name: string }) {
  const kind = name.toLowerCase().endsWith(".docx") ? "DOCX" : "PDF";
  return (
    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-wash text-[10px] font-semibold tracking-wide text-ink-soft ring-1 ring-rule">
      {kind}
    </span>
  );
}

export function DocumentsView() {
  const [documents, setDocuments] = useState<DocumentItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setDocuments(await api.listDocuments());
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Unexpected error");
    }
  }, []);

  // Initial load. setState happens in the promise callbacks (not synchronously in the
  // effect body), which is what the react-hooks lint rule asks for.
  useEffect(() => {
    api
      .listDocuments()
      .then(setDocuments)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Unexpected error"));
  }, []);

  // While a document is still being indexed by the worker, ask again every 3 seconds.
  const pending = documents?.some((d) => d.status === "uploaded" || d.status === "processing");
  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(() => void refresh(), 3000);
    return () => clearInterval(timer);
  }, [pending, refresh]);

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    try {
      await api.uploadDocument(file);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function remove(document: DocumentItem) {
    if (!window.confirm(`Delete "${document.filename}" with its chunks and extractions?`)) return;
    try {
      await api.deleteDocument(document.id);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Delete failed");
    }
  }

  return (
    <>
      <PageHeader title="Documents" description="Upload a contract. It is read and indexed in the background, then you can extract data from it." />

      <input
        ref={fileInput}
        type="file"
        accept=".pdf,.docx"
        className="hidden"
        onChange={(e) => e.target.files?.[0] && void upload(e.target.files[0])}
      />
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const file = e.dataTransfer.files?.[0];
          if (file) void upload(file);
        }}
        className={`mb-8 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-dashed px-6 py-5 transition ${
          dragging ? "border-accent bg-accent-wash" : "border-ink-faint/60 bg-white/60"
        }`}
      >
        <div>
          <p className="text-sm font-medium text-ink">Drop a PDF or DOCX here</p>
          <p className="mt-0.5 text-sm text-ink-soft">or choose a file from your computer.</p>
        </div>
        <div className="flex items-center gap-3">
          {uploading && <Spinner label="Uploading…" />}
          <button className={buttonClass} disabled={uploading} onClick={() => fileInput.current?.click()}>
            Choose file
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-6">
          <ErrorBox>{error}</ErrorBox>
        </div>
      )}

      {documents === null && !error && <Spinner label="Loading…" />}
      {documents?.length === 0 && (
        <EmptyState title="No documents yet">Upload your first contract above to get started.</EmptyState>
      )}

      {documents && documents.length > 0 && (
        <ul className={`divide-y divide-rule ${surfaceClass}`}>
          {documents.map((document) => (
            <li key={document.id} className="flex flex-wrap items-center gap-x-4 gap-y-3 px-5 py-4">
              <FileChip name={document.filename} />
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-ink">{document.filename}</p>
                <p className="mt-0.5 truncate text-sm text-ink-soft">
                  {formatDate(document.created_at)}
                  {document.error && <span className="ml-2 text-bad">{document.error}</span>}
                </p>
              </div>
              <Badge tone={STATUS_TONE[document.status]}>{STATUS_LABEL[document.status]}</Badge>
              <div className="flex items-center gap-1">
                {document.status === "indexed" ? (
                  <Link href={`/documents/${document.id}`} className={buttonClass}>
                    Extract data
                  </Link>
                ) : (
                  <button className={buttonClass} disabled>
                    Extract data
                  </button>
                )}
                <button
                  className="rounded-md px-3 py-2 text-sm text-ink-soft transition hover:bg-bad-wash hover:text-bad"
                  onClick={() => void remove(document)}
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
