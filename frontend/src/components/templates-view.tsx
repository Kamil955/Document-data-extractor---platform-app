"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import type { FieldType, Template } from "@/lib/types";
import { ErrorBox, PageHeader, Spinner, buttonClass, inputClass, secondaryButtonClass } from "./ui";

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
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Saving failed");
    } finally {
      setSaving(false);
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
      <PageHeader title="Templates" />
      {error && <ErrorBox>{error}</ErrorBox>}

      <section className="mb-10 rounded-lg bg-white p-5 shadow-sm ring-1 ring-zinc-200">
        <h2 className="mb-4 text-sm font-semibold text-zinc-900">New template</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <input className={inputClass} placeholder="Name, e.g. Contract basics" value={name} onChange={(e) => setName(e.target.value)} />
          <input className={inputClass} placeholder="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>

        <div className="mt-5 space-y-3">
          {rows.map((row, index) => (
            <div key={index} className="grid gap-2 rounded-md bg-zinc-50 p-3 sm:grid-cols-12">
              <input
                className={`${inputClass} sm:col-span-4`}
                placeholder="Field name, e.g. Governing law"
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
                title="Used as {{key}} in Word templates"
                value={row.key}
                onChange={(e) => updateRow(index, { key: e.target.value, keyTouched: true })}
              />
              <select
                className={`${inputClass} sm:col-span-2`}
                value={row.type}
                onChange={(e) => updateRow(index, { type: e.target.value as FieldType })}
              >
                {FIELD_TYPES.map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
              <button
                className={`${secondaryButtonClass} sm:col-span-3`}
                onClick={() => setRows((current) => (current.length > 1 ? current.filter((_, i) => i !== index) : current))}
                disabled={rows.length === 1}
              >
                Remove
              </button>
              <input
                className={`${inputClass} sm:col-span-12`}
                placeholder="What to look for (optional): which state's law governs the agreement"
                value={row.description}
                onChange={(e) => updateRow(index, { description: e.target.value })}
              />
            </div>
          ))}
        </div>

        {duplicate && <p className="mt-3 text-sm text-red-700">Two fields use the key “{duplicate}”. Keys must be unique.</p>}
        <div className="mt-4 flex items-center gap-3">
          <button className={secondaryButtonClass} onClick={() => setRows((current) => [...current, emptyRow()])}>
            Add field
          </button>
          <button className={buttonClass} disabled={!canSave} onClick={() => void save()}>
            Save template
          </button>
          {saving && <Spinner />}
        </div>
      </section>

      {templates === null && !error && <Spinner label="Loading…" />}
      {templates && templates.length === 0 && (
        <p className="text-sm text-zinc-500">No templates yet. Create the first one above.</p>
      )}
      <ul className="space-y-3">
        {templates?.map((template) => (
          <li key={template.id} className="rounded-lg bg-white p-4 shadow-sm ring-1 ring-zinc-200">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-medium text-zinc-900">{template.name}</p>
                {template.description && <p className="text-sm text-zinc-500">{template.description}</p>}
              </div>
              <button className={secondaryButtonClass} onClick={() => void remove(template)}>
                Delete
              </button>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {template.fields.map((field) => (
                <span key={field.key} title={field.description ?? undefined} className="rounded bg-zinc-100 px-2 py-1 font-mono text-xs text-zinc-700">
                  {`{{${field.key}}}`}
                </span>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
