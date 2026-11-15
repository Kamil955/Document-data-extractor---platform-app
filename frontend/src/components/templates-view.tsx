"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";
import type { FieldType, Template } from "@/lib/types";
import { Badge, EmptyState, ErrorBox, PageHeader, Spinner, buttonClass, inputClass, secondaryButtonClass, surfaceClass } from "./ui";

const FIELD_TYPES: FieldType[] = ["text", "number", "date", "boolean"];

interface Row {
  key: string;
  label: string;
  description: string;
  type: FieldType;
  // Once the person edits the key by hand, stop deriving it from the label.
  keyTouched: boolean;
}

const emptyRow = (): Row => ({ key: "", label: "", description: "", type: "text", keyTouched: false });

// "Termination notice (days)" -> "termination_notice_days". The backend accepts
// [a-z][a-z0-9_]{0,63}: the key becomes the {{placeholder}} in Word templates.
function slugify(label: string): string {
  const slug = label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 64);
  return /^[a-z]/.test(slug) ? slug : slug ? `f_${slug}`.slice(0, 64) : "";
}

export function TemplatesView() {
  const [templates, setTemplates] = useState<Template[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [rows, setRows] = useState<Row[]>([emptyRow()]);
  const [saving, setSaving] = useState(false);
  const wordInput = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);
  // The builder for a template from scratch is folded away until it is asked for.
  const [building, setBuilding] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setTemplates(await api.listTemplates());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Unexpected error");
    }
  }, []);

  // Initial load. setState happens in the promise callbacks, not synchronously in the effect.
  useEffect(() => {
    api
      .listTemplates()
      .then(setTemplates)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Unexpected error"));
  }, []);

  function updateRow(index: number, patch: Partial<Row>) {
    setRows((current) => current.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  const filled = rows.filter((r) => r.label.trim() && r.key.trim());
  const keys = filled.map((r) => r.key);
  const duplicate = keys.find((k, i) => keys.indexOf(k) !== i);
  const canSave = name.trim() !== "" && filled.length > 0 && !duplicate && !saving;

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await api.createTemplate({
        name: name.trim(),
        description: description.trim() || null,
        fields: filled.map((r) => ({
          key: r.key.trim(),
          label: r.label.trim(),
          description: r.description.trim() || null,
          type: r.type,
        })),
      });
      setName("");
      setDescription("");
      setRows([emptyRow()]);
      setBuilding(false);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Saving failed");
    } finally {
      setSaving(false);
    }
  }

  // The fields are read from the {{placeholders}} in the file; the name defaults to the file name.
  async function importDocx(file: File) {
    setImporting(true);
    setError(null);
    try {
      await api.createTemplateFromDocx(file, name.trim() || null);
      setName("");
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Import failed");
    } finally {
      setImporting(false);
    }
  }

  async function remove(template: Template) {
    if (!window.confirm(`Delete template "${template.name}"? Saved extractions are kept.`)) return;
    try {
      await api.deleteTemplate(template.id);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Delete failed");
    }
  }

  return (
    <>
      <PageHeader
        title="Templates"
        description="A template lists the fields to extract and, optionally, the Word document they are filled into."
      >
        <input
          ref={wordInput}
          type="file"
          accept=".docx"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (file) void importDocx(file);
          }}
        />
        {importing && <Spinner />}
        <button
          className={secondaryButtonClass}
          disabled={importing}
          title="Every {{placeholder}} in the file becomes a field"
          onClick={() => wordInput.current?.click()}
        >
          From a Word file
        </button>
        <button className={buttonClass} onClick={() => setBuilding((open) => !open)} aria-expanded={building}>
          {building ? "Close" : "New template"}
        </button>
      </PageHeader>

      {error && (
        <div className="mb-6">
          <ErrorBox>{error}</ErrorBox>
        </div>
      )}

      {building && (
        <section className={`mb-8 px-6 py-6 ${surfaceClass}`}>
          <h2 className="font-semibold text-ink">New template</h2>
          <p className="mt-1 text-sm text-ink-soft">
            Name the fields you want to read from a document. You can write the Word document afterwards.
          </p>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            <input className={inputClass} placeholder="Name, e.g. Contract basics" value={name} onChange={(e) => setName(e.target.value)} aria-label="Template name" />
            <input className={inputClass} placeholder="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} aria-label="Description" />
          </div>

          <div className="mt-6 space-y-3">
            {rows.map((row, index) => (
              <div key={index} className="grid gap-2 rounded-lg bg-wash p-3 sm:grid-cols-12">
                <input
                  className={`${inputClass} sm:col-span-5`}
                  placeholder="Field name, e.g. Governing law"
                  aria-label="Field name"
                  value={row.label}
                  onChange={(e) =>
                    updateRow(index, {
                      label: e.target.value,
                      ...(row.keyTouched ? {} : { key: slugify(e.target.value) }),
                    })
                  }
                />
                <input
                  className={`${inputClass} font-mono sm:col-span-3`}
                  placeholder="key"
                  aria-label="Field key"
                  title="Used as {{key}} in Word templates"
                  value={row.key}
                  onChange={(e) => updateRow(index, { key: e.target.value, keyTouched: true })}
                />
                <select
                  className={`${inputClass} sm:col-span-2`}
                  aria-label="Field type"
                  value={row.type}
                  onChange={(e) => updateRow(index, { type: e.target.value as FieldType })}
                >
                  {FIELD_TYPES.map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
                <button
                  className="rounded-md px-3 py-2 text-sm text-ink-soft transition hover:bg-bad-wash hover:text-bad disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-ink-soft sm:col-span-2"
                  onClick={() => setRows((current) => (current.length > 1 ? current.filter((_, i) => i !== index) : current))}
                  disabled={rows.length === 1}
                >
                  Remove
                </button>
                <input
                  className={`${inputClass} sm:col-span-12`}
                  placeholder="What to look for (optional): which state's law governs the agreement"
                  aria-label="What to look for"
                  value={row.description}
                  onChange={(e) => updateRow(index, { description: e.target.value })}
                />
              </div>
            ))}
          </div>

          {duplicate && <p className="mt-3 text-sm text-bad">Two fields use the key “{duplicate}”. Keys must be unique.</p>}
          <div className="mt-5 flex items-center gap-3">
            <button className={secondaryButtonClass} onClick={() => setRows((current) => [...current, emptyRow()])}>
              Add field
            </button>
            <button className={buttonClass} disabled={!canSave} onClick={() => void save()}>
              Save template
            </button>
            {saving && <Spinner />}
          </div>
        </section>
      )}

      {templates === null && !error && <Spinner label="Loading…" />}
      {templates && templates.length === 0 && (
        <EmptyState title="No templates yet">
          Create one with <strong className="font-medium text-ink">New template</strong>, or start from a Word file that
          already has {"{{placeholders}}"}.
        </EmptyState>
      )}
      {templates && templates.length > 0 && (
        <ul className={`divide-y divide-rule ${surfaceClass}`}>
          {templates.map((template) => (
            <li key={template.id} className="px-6 py-5">
              <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2.5">
                    <Link href={`/templates/${template.id}`} className="font-semibold text-ink hover:underline">
                      {template.name}
                    </Link>
                    {template.docx_filename ? <Badge tone="ok">Word document</Badge> : <Badge>No document</Badge>}
                  </p>
                  {template.description && <p className="mt-1 text-sm text-ink-soft">{template.description}</p>}
                </div>
                <div className="flex items-center gap-1">
                  <Link href={`/templates/${template.id}`} className={secondaryButtonClass}>
                    Open
                  </Link>
                  <button
                    className="rounded-md px-3 py-2 text-sm text-ink-soft transition hover:bg-bad-wash hover:text-bad"
                    onClick={() => void remove(template)}
                  >
                    Delete
                  </button>
                </div>
              </div>
              <p className="mt-3 flex flex-wrap items-center gap-1.5">
                <span className="mr-1 text-sm text-ink-soft">{template.fields.length} fields</span>
                {template.fields.slice(0, 6).map((field) => (
                  <span key={field.key} title={field.description ?? undefined} className="rounded bg-wash px-2 py-0.5 font-mono text-xs text-ink-soft ring-1 ring-rule">
                    {field.key}
                  </span>
                ))}
                {template.fields.length > 6 && <span className="text-xs text-ink-faint">+{template.fields.length - 6} more</span>}
              </p>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
