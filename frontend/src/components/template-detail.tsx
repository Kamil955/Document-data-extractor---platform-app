"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { download } from "@/lib/download";
import type { Template, TemplatePreview } from "@/lib/types";
import { PlaceholderChips, TemplatePreviewView } from "./template-preview";
import { ErrorBox, PageHeader, Spinner, buttonClass, secondaryButtonClass, surfaceClass } from "./ui";

const message = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

export function TemplateDetail() {
  const { id } = useParams<{ id: string }>();
  const input = useRef<HTMLInputElement>(null);
  const [template, setTemplate] = useState<Template | null>(null);
  const [preview, setPreview] = useState<TemplatePreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // The preview exists only while the template has a document.
  const fetchAll = useCallback(async () => {
    const loaded = await api.getTemplate(id);
    return { loaded, preview: loaded.docx_filename ? await api.getTemplatePreview(id) : null };
  }, [id]);

  const load = useCallback(async () => {
    const { loaded, preview } = await fetchAll();
    setTemplate(loaded);
    setPreview(preview);
  }, [fetchAll]);

  // Initial load: setState only in the promise callbacks, not synchronously in the effect.
  useEffect(() => {
    fetchAll()
      .then(({ loaded, preview }) => {
        setTemplate(loaded);
        setPreview(preview);
      })
      .catch((e) => setError(message(e, "Unexpected error")));
  }, [fetchAll]);

  // Runs one action, then reloads template and preview.
  async function act(action: () => Promise<unknown>, failure: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await load();
    } catch (e) {
      setError(message(e, failure));
    } finally {
      setBusy(false);
    }
  }

  async function downloadDocument() {
    if (!template?.docx_filename) return;
    try {
      download(await api.downloadTemplateDocx(id), template.docx_filename);
    } catch (e) {
      setError(message(e, "Download failed"));
    }
  }

  if (error && !template) return <ErrorBox>{error}</ErrorBox>;
  if (!template) return <Spinner label="Loading…" />;

  const unknown = preview?.placeholders.filter((p) => !p.known) ?? [];

  return (
    <>
      <PageHeader title={template.name} description={template.description ?? undefined} back={{ href: "/templates", label: "Templates" }} />
      {error && (
        <div className="mb-6">
          <ErrorBox>{error}</ErrorBox>
        </div>
      )}

      <section className="mb-10">
        <h2 className="mb-3 text-sm font-semibold text-ink">Fields</h2>
        <ul className={`divide-y divide-rule text-sm ${surfaceClass}`}>
          {template.fields.map((field) => (
            <li key={field.key} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 px-6 py-3.5">
              <span className="w-44 shrink-0 font-medium text-ink">{field.label}</span>
              <code className="rounded bg-wash px-1.5 py-0.5 font-mono text-xs text-ink-soft ring-1 ring-rule">{`{{${field.key}}}`}</code>
              <span className="text-xs text-ink-faint">{field.type}</span>
              {field.description && <span className="text-ink-soft">{field.description}</span>}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-ink">
            Word document{template.docx_filename && <span className="ml-2 font-normal text-ink-soft">{template.docx_filename}</span>}
          </h2>
          <div className="flex flex-wrap items-center gap-2">
            <input
              ref={input}
              type="file"
              accept=".docx"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = ""; // allow choosing the same file again
                if (file) void act(() => api.putTemplateDocx(id, file), "Upload failed");
              }}
            />
            <Link href={`/templates/${id}/edit`} className={buttonClass}>
              {template.docx_filename ? "Edit document" : "Write the document"}
            </Link>
            {!template.docx_filename && (
              <button className={secondaryButtonClass} disabled={busy} onClick={() => void act(() => api.generateTemplateDocx(id), "Generating failed")}>
                Generate a starter document
              </button>
            )}
            <button className={secondaryButtonClass} disabled={busy} onClick={() => input.current?.click()}>
              {template.docx_filename ? "Replace…" : "Upload .docx…"}
            </button>
            {template.docx_filename && (
              <button className={secondaryButtonClass} onClick={() => void downloadDocument()}>
                Download
              </button>
            )}
            {busy && <Spinner />}
          </div>
        </div>

        {!template.docx_filename && (
          <p className={`px-6 py-5 text-sm leading-relaxed text-ink-soft ${surfaceClass}`}>
            This template has no document yet. Write it in the editor here, generate a starter one from the fields, or upload your
            own .docx with placeholders such as <code className="font-mono">{"{{governing_law}}"}</code>.
          </p>
        )}

        {preview && (
          <>
            <div className="mb-3 space-y-2 text-sm">
              <PlaceholderChips placeholders={preview.placeholders} />
              {preview.placeholders.length === 0 && (
                <p className="text-warn">The document has no {"{{placeholders}}"}, so filling would change nothing.</p>
              )}
              {unknown.length > 0 && (
                <p className="text-bad">
                  No field has the key {unknown.map((p) => `“${p.key}”`).join(", ")}: these placeholders will stay as they are.
                </p>
              )}
              {preview.unused_fields.length > 0 && (
                <p className="text-warn">
                  Fields missing from the document: {preview.unused_fields.join(", ")}.
                </p>
              )}
            </div>
            <TemplatePreviewView preview={preview} />
          </>
        )}
      </section>
    </>
  );
}
