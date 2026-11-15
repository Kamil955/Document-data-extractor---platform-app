"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import type { DocumentItem, Template } from "@/lib/types";
import { ExtractionsList } from "./extractions-list";
import { ErrorBox, PageHeader, Spinner, buttonClass, inputClass, surfaceClass } from "./ui";

export function ExtractView() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [document, setDocument] = useState<DocumentItem | null>(null);
  const [templates, setTemplates] = useState<Template[] | null>(null);
  const [templateId, setTemplateId] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.getDocument(id), api.listTemplates()])
      .then(([doc, list]) => {
        setDocument(doc);
        setTemplates(list);
        if (list.length > 0) setTemplateId(list[0].id);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Unexpected error"));
  }, [id]);

  const selected = templates?.find((t) => t.id === templateId);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      const extraction = await api.extract(id, templateId);
      router.push(`/extractions/${extraction.extraction_id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start the extraction");
      setRunning(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Extract data"
        description="Choose a template and start. The work runs in the background, so you can leave this page."
        back={{ href: "/", label: "Documents" }}
      />
      {error && (
        <div className="mb-6">
          <ErrorBox>{error}</ErrorBox>
        </div>
      )}
      {!document && !error && <Spinner label="Loading…" />}

      {document && templates && (
        <div className={`px-6 py-6 ${surfaceClass}`}>
          <p className="text-sm text-ink-soft">Document</p>
          <p className="mt-0.5 font-medium text-ink">{document.filename}</p>

          {templates.length === 0 ? (
            <p className="mt-6 text-sm text-ink-soft">
              You need a template first.{" "}
              <Link href="/templates" className="font-medium text-accent underline-offset-2 hover:underline">
                Create one
              </Link>
              .
            </p>
          ) : (
            <>
              <label className="mt-6 mb-1.5 block text-sm text-ink-soft" htmlFor="template">
                Template
              </label>
              <select
                id="template"
                value={templateId}
                disabled={running}
                onChange={(e) => setTemplateId(e.target.value)}
                className={`${inputClass} max-w-md`}
              >
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.fields.length} fields)
                  </option>
                ))}
              </select>

              {selected && (
                <p className="mt-4 flex flex-wrap gap-1.5">
                  {selected.fields.map((field) => (
                    <span key={field.key} className="rounded-full bg-wash px-2.5 py-0.5 text-xs text-ink-soft ring-1 ring-rule">
                      {field.label}
                    </span>
                  ))}
                </p>
              )}

              <div className="mt-6 flex flex-wrap items-center gap-4">
                <button className={buttonClass} disabled={running || !templateId} onClick={() => void run()}>
                  Start extraction
                </button>
                {running && <Spinner label="Starting…" />}
                {selected && !running && (
                  <span className="text-sm text-ink-soft">
                    About {selected.fields.length * 3}–{selected.fields.length * 5} seconds on a local model.
                  </span>
                )}
              </div>
            </>
          )}
        </div>
      )}
      {document && <ExtractionsList documentId={id} />}
    </>
  );
}
