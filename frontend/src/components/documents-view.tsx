"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";
import type { DocumentItem, DocumentStatus } from "@/lib/types";
import { Badge, ErrorBox, PageHeader, Spinner, buttonClass, secondaryButtonClass } from "./ui";

const STATUS_STYLE: Record<DocumentStatus, string> = {
  uploaded: "bg-zinc-100 text-zinc-600 ring-zinc-500/20",
  processing: "bg-sky-50 text-sky-700 ring-sky-600/20",
  indexed: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  failed: "bg-red-50 text-red-700 ring-red-600/20",
};
const STATUS_LABEL: Record<DocumentStatus, string> = {
  uploaded: "Queued",
  processing: "Processing",
  indexed: "Ready",
  failed: "Failed",
};

export function DocumentsView() {
  const [documents, setDocuments] = useState<DocumentItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

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
      <PageHeader title="Documents">
        <div className="flex items-center gap-3">
          {uploading && <Spinner label="Uploading…" />}
          <input
            ref={fileInput}
            type="file"
            accept=".pdf,.docx"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && void upload(e.target.files[0])}
          />
          <button className={buttonClass} disabled={uploading} onClick={() => fileInput.current?.click()}>
            Upload PDF or DOCX
          </button>
        </div>
      </PageHeader>

      {error && <ErrorBox>{error}</ErrorBox>}

      {documents === null && !error && <Spinner label="Loading…" />}
      {documents?.length === 0 && (
        <p className="rounded-lg border border-dashed border-zinc-300 p-10 text-center text-sm text-zinc-500">
          No documents yet. Upload a contract to get started.
        </p>
      )}

      {documents && documents.length > 0 && (
        <ul className="divide-y divide-zinc-200 rounded-lg bg-white shadow-sm ring-1 ring-zinc-200">
          {documents.map((document) => (
            <li key={document.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-zinc-900">{document.filename}</p>
                <p className="mt-0.5 text-xs text-zinc-500">
                  {new Date(document.created_at).toLocaleString()}
                  {document.error && <span className="ml-2 text-red-600">{document.error}</span>}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Badge className={STATUS_STYLE[document.status]}>{STATUS_LABEL[document.status]}</Badge>
                {document.status === "indexed" ? (
                  <Link href={`/documents/${document.id}`} className={buttonClass}>
                    Extract data
                  </Link>
                ) : (
                  <button className={buttonClass} disabled>
                    Extract data
                  </button>
                )}
                <button className={secondaryButtonClass} onClick={() => void remove(document)}>
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
