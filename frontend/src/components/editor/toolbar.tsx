"use client";

import type { Editor } from "@tiptap/core";
import { useEditorState } from "@tiptap/react";
import type { ReactNode } from "react";
import { ListIcon, RedoIcon, TableIcon, UndoIcon } from "./icons";

function Tool({
  label,
  active,
  disabled,
  onClick,
  children,
}: {
  label: string;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={active}
      disabled={disabled}
      // The editor keeps its selection: pressing a toolbar button must not take the focus.
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      className={`inline-flex h-8 min-w-8 items-center justify-center rounded-md px-2 text-sm transition focus-visible:outline-2 focus-visible:outline-[var(--accent)] disabled:opacity-30 ${
        active ? "bg-[var(--accent-soft)] text-[var(--accent)]" : "text-[var(--ink)] hover:bg-[#eef0f8]"
      }`}
    >
      {children}
    </button>
  );
}

const Divider = () => <span className="mx-1.5 h-5 w-px bg-[var(--rule)]" aria-hidden />;

type BlockKind = "paragraph" | "title" | "h1" | "h2" | "h3" | "h4";

function currentBlock(editor: Editor): BlockKind {
  for (const level of [1, 2, 3, 4] as const) if (editor.isActive("heading", { level })) return `h${level}`;
  return editor.isActive("paragraph", { title: true }) ? "title" : "paragraph";
}

function setBlock(editor: Editor, kind: BlockKind) {
  const chain = editor.chain().focus();
  if (kind === "paragraph") chain.setParagraph().updateAttributes("paragraph", { title: false }).run();
  else if (kind === "title") chain.setParagraph().updateAttributes("paragraph", { title: true }).run();
  else chain.setHeading({ level: Number(kind[1]) as 1 | 2 | 3 | 4 }).run();
}

export function Toolbar({ editor }: { editor: Editor }) {
  const state = useEditorState({
    editor,
    selector: ({ editor }) => ({
      block: currentBlock(editor),
      bold: editor.isActive("bold"),
      italic: editor.isActive("italic"),
      underline: editor.isActive("underline"),
      list: editor.isActive("bulletList"),
      inTable: editor.isActive("table"),
      canUndo: editor.can().undo(),
      canRedo: editor.can().redo(),
    }),
  });

  return (
    <div role="toolbar" aria-label="Formatting" className="flex flex-wrap items-center gap-0.5 border-b border-[var(--rule)] bg-white px-4 py-2">
      <Tool label="Undo (Ctrl+Z)" disabled={!state.canUndo} onClick={() => editor.chain().focus().undo().run()}>
        <UndoIcon />
      </Tool>
      <Tool label="Redo (Ctrl+Shift+Z)" disabled={!state.canRedo} onClick={() => editor.chain().focus().redo().run()}>
        <RedoIcon />
      </Tool>
      <Divider />
      <select
        aria-label="Paragraph style"
        value={state.block}
        onChange={(e) => setBlock(editor, e.target.value as BlockKind)}
        className="h-8 rounded-md border-0 bg-transparent px-2 text-sm text-[var(--ink)] ring-1 ring-inset ring-[var(--rule)] hover:bg-[#eef0f8] focus-visible:outline-2 focus-visible:outline-[var(--accent)]"
      >
        <option value="paragraph">Text</option>
        <option value="title">Title</option>
        <option value="h1">Heading 1</option>
        <option value="h2">Heading 2</option>
        <option value="h3">Heading 3</option>
        <option value="h4">Heading 4</option>
      </select>
      <Divider />
      <Tool label="Bold (Ctrl+B)" active={state.bold} onClick={() => editor.chain().focus().toggleBold().run()}>
        <span className="font-bold">B</span>
      </Tool>
      <Tool label="Italic (Ctrl+I)" active={state.italic} onClick={() => editor.chain().focus().toggleItalic().run()}>
        <span className="italic">I</span>
      </Tool>
      <Tool label="Underline (Ctrl+U)" active={state.underline} onClick={() => editor.chain().focus().toggleUnderline().run()}>
        <span className="underline">U</span>
      </Tool>
      <Divider />
      <Tool label="Bulleted list" active={state.list} onClick={() => editor.chain().focus().toggleBulletList().run()}>
        <ListIcon />
      </Tool>
      <Tool
        label="Insert table"
        disabled={state.inTable}
        onClick={() => editor.chain().focus().insertTable({ rows: 3, cols: 2, withHeaderRow: false }).run()}
      >
        <TableIcon />
      </Tool>

      {state.inTable && (
        <>
          <Divider />
          <span className="px-1 text-xs text-[var(--ink-soft)]">Table</span>
          <Tool label="Add row below" onClick={() => editor.chain().focus().addRowAfter().run()}>
            + Row
          </Tool>
          <Tool label="Add column to the right" onClick={() => editor.chain().focus().addColumnAfter().run()}>
            + Column
          </Tool>
          <Tool label="Delete row" onClick={() => editor.chain().focus().deleteRow().run()}>
            − Row
          </Tool>
          <Tool label="Delete column" onClick={() => editor.chain().focus().deleteColumn().run()}>
            − Column
          </Tool>
          <Tool label="Delete table" onClick={() => editor.chain().focus().deleteTable().run()}>
            Delete table
          </Tool>
        </>
      )}
    </div>
  );
}
