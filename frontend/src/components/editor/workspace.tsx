"use client";

import "./editor.css";
import { getTextBetween, getTextSerializersFromSchema } from "@tiptap/core";
import type { Editor } from "@tiptap/core";
import { TextSelection } from "@tiptap/pm/state";
import { EditorContent, useEditor } from "@tiptap/react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { blocksToEditor, editorToBlocks, placeholderCounts, textToNodes } from "@/lib/editor-model";
import type { PreviewParagraph, PreviewTable, Template } from "@/lib/types";
import { AiPanel } from "./ai-panel";
import { aiTargetKey } from "./ai-highlight";
import { extensions } from "./extensions";
import { FieldsPanel } from "./fields-panel";
import { SparkIcon } from "./icons";
import { Toolbar } from "./toolbar";

// The most text the backend accepts for one rewrite (see RewriteRequest).
const MAX_REWRITE_CHARS = 4000;
const MAX_CONTEXT_CHARS = 3000;

interface Range {
  from: number;
  to: number;
}

interface AiSession extends Range {
  text: string;
  context: string | null;
  marks: { type: string; attrs?: Record<string, unknown> }[];
}

function textBetween(editor: Editor, range: Range): string {
  // The serializers turn a placeholder node back into {{key}}.
  return getTextBetween(editor.state.doc, range, { textSerializers: getTextSerializersFromSchema(editor.schema), blockSeparator: "\n" });
}

// Viewport position of a range, for the floating controls.
function rectOf(editor: Editor, range: Range): { top: number; bottom: number; left: number } | null {
  try {
    const start = editor.view.coordsAtPos(range.from);
    const end = editor.view.coordsAtPos(range.to);
    return { top: start.top, bottom: end.bottom, left: start.left };
  } catch {
    return null;
  }
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(value, max));
}

export function EditorWorkspace({
  template,
  initialBlocks,
  notes,
}: {
  template: Template;
  initialBlocks: (PreviewParagraph | PreviewTable)[];
  notes: string[];
}) {
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showNotes, setShowNotes] = useState(true);
  const [counts, setCounts] = useState(() => placeholderCounts(blocksToEditor(initialBlocks)));
  // The selected passage (when it can be sent to the AI) and the open AI session.
  const [selection, setSelection] = useState<Range | null>(null);
  const [ai, setAi] = useState<AiSession | null>(null);
  // Bumped when the page scrolls or resizes, so floating controls follow their text.
  const [, setTick] = useState(0);

  const closeAi = useCallback((editor: Editor | null) => {
    setAi(null);
    if (editor) editor.view.dispatch(editor.state.tr.setMeta(aiTargetKey, null));
  }, []);

  const editor = useEditor({
    extensions,
    content: blocksToEditor(initialBlocks),
    // Next renders on the server first; the editor only exists in the browser.
    immediatelyRender: false,
    editorProps: { attributes: { "aria-label": "Template document", spellcheck: "true" } },
    onUpdate: ({ editor }) => {
      setDirty(true);
      setCounts(placeholderCounts(editor.getJSON()));
    },
    onSelectionUpdate: ({ editor }) => {
      const { selection: current } = editor.state;
      const usable =
        current instanceof TextSelection && !current.empty && current.$from.sameParent(current.$to) && current.$from.parent.isTextblock;
      setSelection(usable ? { from: current.from, to: current.to } : null);
      // Clicking elsewhere in the document ends the AI session.
      if (aiTargetKey.getState(editor.state)) closeAi(editor);
    },
  });

  const openAi = useCallback(() => {
    if (!editor || !selection) return;
    const text = textBetween(editor, selection);
    if (!text.trim() || text.length > MAX_REWRITE_CHARS) return;
    const $from = editor.state.doc.resolve(selection.from);
    const paragraph = textBetween(editor, { from: $from.start(), to: $from.end() });
    const marks = ($from.marksAcross(editor.state.doc.resolve(selection.to)) ?? []).map((m) => m.toJSON());
    editor.view.dispatch(editor.state.tr.setMeta(aiTargetKey, { from: selection.from, to: selection.to }));
    setAi({
      ...selection,
      text,
      // The paragraph around the passage helps the model keep the tone; skip it when it is the passage itself.
      context: paragraph.trim() === text.trim() ? null : paragraph.slice(0, MAX_CONTEXT_CHARS),
      marks,
    });
  }, [editor, selection]);

  const applyAi = useCallback(
    (text: string) => {
      if (!editor || !ai) return;
      const range = aiTargetKey.getState(editor.state);
      // The passage may have been edited while the model was working: do not overwrite new text.
      if (!range || textBetween(editor, range) !== ai.text) {
        setError("The selected text changed while the AI was working. Select it again and retry.");
        closeAi(editor);
        return;
      }
      closeAi(editor);
      editor.chain().focus().insertContentAt(range, textToNodes(text, ai.marks)).run();
    },
    [editor, ai, closeAi],
  );

  const save = useCallback(async () => {
    if (!editor || saving) return;
    setSaving(true);
    setError(null);
    try {
      await api.putTemplateContent(template.id, editorToBlocks(editor.getJSON()));
      setDirty(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Saving failed. Try again.");
    } finally {
      setSaving(false);
    }
  }, [editor, saving, template.id]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (!(event.metaKey || event.ctrlKey)) return;
      if (event.key === "s") {
        event.preventDefault();
        void save();
      } else if (event.key === "k" && selection) {
        event.preventDefault();
        openAi();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [save, openAi, selection]);

  useEffect(() => {
    if (!dirty) return;
    // The browser's own "leave site?" prompt for unsaved work.
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  useEffect(() => {
    const bump = () => setTick((n) => n + 1);
    window.addEventListener("resize", bump);
    return () => window.removeEventListener("resize", bump);
  }, []);

  // Placeholders that are not fields of this template are drawn red. The keys are [a-z0-9_]
  // only (the backend enforces it), so they are safe to put in a selector.
  const unknownStyle = `.te-paper .ph${template.fields.map((f) => `:not([data-placeholder="${f.key}"])`).join("")} {
    background: var(--bad-bg); border-color: var(--bad-rule); color: var(--bad-ink); }`;

  const anchor = ai ?? selection;
  const rect = editor && anchor ? rectOf(editor, anchor) : null;

  return (
    <div className="te fixed inset-0 z-50 flex flex-col bg-[var(--desk)] text-[var(--ink)]">
      <style>{unknownStyle}</style>

      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-[var(--rule)] bg-white px-4">
        <Link
          href={`/templates/${template.id}`}
          aria-label="Back to the template"
          onClick={(e) => {
            if (dirty && !window.confirm("You have unsaved changes. Leave without saving?")) e.preventDefault();
          }}
          className="rounded-md p-2 text-[var(--ink-soft)] transition hover:bg-[#eef0f8] hover:text-[var(--ink)]"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M10 3 5 8l5 5" />
          </svg>
        </Link>
        <h1 className="truncate text-sm font-semibold">{template.name}</h1>

        <div className="ml-auto flex items-center gap-4">
          <span role="status" className="flex items-center gap-2 text-xs text-[var(--ink-soft)]">
            <span className={`h-1.5 w-1.5 rounded-full ${saving ? "bg-[var(--accent)]" : dirty ? "bg-amber-500" : "bg-emerald-500"}`} aria-hidden />
            {saving ? "Saving…" : dirty ? "Unsaved changes" : "All changes saved"}
          </span>
          <button
            type="button"
            onClick={() => void save()}
            disabled={saving || !dirty}
            title="Save (Ctrl+S)"
            className="rounded-md bg-[var(--ink)] px-4 py-1.5 text-sm font-medium text-white transition hover:bg-[#2b3350] disabled:opacity-40"
          >
            Save
          </button>
        </div>
      </header>

      {editor && <Toolbar editor={editor} />}

      <div className="flex min-h-0 flex-1">
        <div className="hidden lg:flex">
          <FieldsPanel
            fields={template.fields}
            counts={counts}
            onInsert={(key) => editor?.chain().focus().insertContent({ type: "placeholder", attrs: { key } }).run()}
          />
        </div>

        <div className="relative min-w-0 flex-1 overflow-y-auto" onScroll={() => setTick((n) => n + 1)}>
          {(error || (showNotes && notes.length > 0)) && (
            <div className="mx-auto mt-6 w-[794px] max-w-[calc(100%-2rem)] space-y-2">
              {error && (
                <div role="alert" className="flex items-start justify-between gap-3 rounded-lg bg-[var(--bad-bg)] px-4 py-3 text-sm text-[var(--bad-ink)]">
                  <span>{error}</span>
                  <button type="button" onClick={() => setError(null)} className="shrink-0 font-medium underline">
                    Dismiss
                  </button>
                </div>
              )}
              {showNotes && notes.length > 0 && (
                <div className="flex items-start justify-between gap-3 rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-900 ring-1 ring-amber-600/20">
                  <div>
                    <p className="font-medium">Saving from here changes this file</p>
                    <ul className="mt-1 list-disc pl-5">
                      {notes.map((note) => (
                        <li key={note}>{note}</li>
                      ))}
                    </ul>
                  </div>
                  <button type="button" onClick={() => setShowNotes(false)} className="shrink-0 font-medium underline">
                    Got it
                  </button>
                </div>
              )}
            </div>
          )}

          <div className="te-paper mx-auto my-8 w-[794px] max-w-[calc(100%-2rem)] bg-white px-6 py-10 sm:px-[72px] sm:py-[72px]">
            <EditorContent editor={editor} />
          </div>
        </div>
      </div>

      {editor && rect && ai && (
        <div className="fixed z-[60]" style={{ top: clamp(rect.bottom + 10, 8, window.innerHeight - 420), left: clamp(rect.left, 12, window.innerWidth - 436) }}>
          <AiPanel key={`${ai.from}-${ai.to}`} target={{ text: ai.text, context: ai.context }} onApply={applyAi} onClose={() => { closeAi(editor); editor.commands.focus(); }} />
        </div>
      )}

      {editor && rect && !ai && selection && (
        <div className="te-pop fixed z-[60]" style={{ top: clamp(rect.bottom + 8, 8, window.innerHeight - 56), left: clamp(rect.left, 12, window.innerWidth - 240) }}>
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={openAi}
            disabled={textBetween(editor, selection).length > MAX_REWRITE_CHARS}
            title="Edit the selected text with AI (Ctrl+K)"
            className="inline-flex items-center gap-2 rounded-full bg-[var(--ink)] py-1.5 pr-3.5 pl-3 text-sm font-medium text-white shadow-[0_8px_20px_-8px_rgba(26,32,51,0.6)] transition hover:bg-[#2b3350] disabled:opacity-50"
          >
            <SparkIcon />
            Ask AI
            <span className="text-xs font-normal text-white/60">Ctrl K</span>
          </button>
        </div>
      )}
    </div>
  );
}
