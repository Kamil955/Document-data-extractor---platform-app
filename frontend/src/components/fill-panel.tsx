"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ApiError, api } from "@/lib/api";
import { download } from "@/lib/download";
import type { FillReport, Template } from "@/lib/types";
import { ErrorBox, Spinner, buttonClass, secondaryButtonClass } from "./ui";

export function FillPanel({ extractionId, templateId }: { extractionId: string; templateId: string | null }) {
  const input = useRef<HTMLInputElement>(null);
  const [template, setTemplate] = useState<Template | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<FillReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Does the extraction's template have its own document? Then no upload is needed.
  useEffect(() => {
    if (!templateId) return;
    api
      .getTemplate(templateId)
      .then(setTemplate)
      .catch(() => setTemplate(null)); // deleted template: fall back to uploading a file
  }, [templateId]);

  const stored = template?.docx_filename ?? null;

  // `own` = fill the file picked here instead of the template's document.
  async function fill(own: File | null) {
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      const result = await api.fillTemplate(extractionId, own ?? undefined);
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
        Values you confirmed or corrected above are used. Missing values are marked yellow, unchecked ones turquoise.
      </p>

      {stored && template && (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button className={buttonClass} disabled={busy} onClick={() => void fill(null)}>
            Fill “{stored}” and download
          </button>
          <Link href={`/templates/${template.id}`} className="text-sm text-zinc-500 underline hover:text-zinc-900">
            Preview the template
          </Link>
        </div>
      )}

      <p className="mt-4 text-sm text-zinc-500">
        {stored ? "Or use another file for this one time:" : (
          <>
            Upload a .docx with placeholders such as <code className="font-mono">{"{{governing_law}}"}</code>
            {templateId && " (or attach a document to the template once, on its page)"}.
          </>
        )}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <input ref={input} type="file" accept=".docx" className="hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <button className={secondaryButtonClass} onClick={() => input.current?.click()}>
          {file ? file.name : "Choose .docx file"}
        </button>
        <button className={stored ? secondaryButtonClass : buttonClass} disabled={!file || busy} onClick={() => void fill(file)}>
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
