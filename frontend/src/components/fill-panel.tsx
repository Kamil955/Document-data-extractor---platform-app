"use client";

import { useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";
import type { FillReport } from "@/lib/types";
import { ErrorBox, Spinner, buttonClass, secondaryButtonClass } from "./ui";

// Hands a Blob to the browser as a file download.
function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function FillPanel({ extractionId }: { extractionId: string }) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<FillReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function fill() {
    if (!file) return;
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      const result = await api.fillTemplate(extractionId, file);
      download(result.blob, result.filename);
      setReport(result.report);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Filling failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mt-10 rounded-lg bg-white p-5 shadow-sm ring-1 ring-zinc-200">
      <h2 className="text-sm font-semibold text-zinc-900">Fill a Word template</h2>
      <p className="mt-1 text-sm text-zinc-500">
        Upload a .docx with placeholders such as <code className="font-mono">{"{{governing_law}}"}</code>. Values you
        confirmed or corrected above are used. Missing values are marked yellow, unchecked ones turquoise.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <input ref={input} type="file" accept=".docx" className="hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <button className={secondaryButtonClass} onClick={() => input.current?.click()}>
          {file ? file.name : "Choose .docx file"}
        </button>
        <button className={buttonClass} disabled={!file || busy} onClick={() => void fill()}>
          Fill and download
        </button>
        {busy && <Spinner />}
      </div>

      {error && (
        <div className="mt-3">
          <ErrorBox>{error}</ErrorBox>
        </div>
      )}
      {report && (
        <ul className="mt-4 space-y-1 text-sm text-zinc-700">
          <li>{report.filled} placeholders filled.</li>
          {report.unverified.length > 0 && <li>Not verified (turquoise): {report.unverified.join(", ")}</li>}
          {report.missing.length > 0 && <li>Not found (yellow): {report.missing.join(", ")}</li>}
          {report.unknown.length > 0 && <li>No such field, left as is: {report.unknown.join(", ")}</li>}
        </ul>
      )}
    </section>
  );
}
