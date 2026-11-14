"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import type { DocumentItem, Template } from "@/lib/types";
import { ErrorBox, PageHeader, Spinner, buttonClass } from "./ui";

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
      setError(e instanceof ApiError ? e.message : "Extraction failed");
      setRunning(false);
    }
  }

  return (
    <>
      <PageHeader title="Extract data">
        <Link href="/" className="text-sm text-zinc-600 hover:text-zinc-900">
          ← Documents
        </Link>
      </PageHeader>
      {error && <ErrorBox>{error}</ErrorBox>}
      {!document && !error && <Spinner label="Loading…" />}

      {document && templates && (
        <div className="rounded-lg bg-white p-5 shadow-sm ring-1 ring-zinc-200">
          <p className="text-sm text-zinc-500">Document</p>
          <p className="mb-5 font-medium text-zinc-900">{document.filename}</p>

          {templates.length === 0 ? (
            <p className="text-sm text-zinc-600">
              You need a template first.{" "}
              <Link href="/templates" className="font-medium underline">
                Create one
              </Link>
              .
            </p>
          ) : (
            <>
              <label className="mb-1 block text-sm text-zinc-500" htmlFor="template">
                Template
              </label>
              <select
                id="template"
                value={templateId}
                disabled={running}
                onChange={(e) => setTemplateId(e.target.value)}
                className="w-full max-w-md rounded-md border-0 bg-white px-3 py-2 text-sm ring-1 ring-inset ring-zinc-300"
              >
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.fields.length} fields)
                  </option>
                ))}
              </select>

              <div className="mt-5 flex items-center gap-4">
                <button className={buttonClass} disabled={running || !templateId} onClick={() => void run()}>
                  Run extraction
                </button>
                {running && selected && (
                  <Spinner label={`Reading the document… about ${selected.fields.length * 3}–${selected.fields.length * 5} seconds`} />
                )}
              </div>
            </>
          )}
        </div>
      )}
    </>
  );
}
