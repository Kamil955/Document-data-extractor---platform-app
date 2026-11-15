"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { CloseIcon, SparkIcon } from "./icons";

const PRESETS = ["Make it more formal", "Make it shorter", "Simplify the wording", "Fix grammar and typos"];

export interface AiTargetText {
  text: string;
  context: string | null;
}

// The prompt box that opens next to selected text: type what to change (or pick a preset),
// read the suggestion, then replace the selection or discard it. The document is never
// changed without the person pressing "Replace".
export function AiPanel({
  target,
  onApply,
  onClose,
}: {
  target: AiTargetText;
  onApply: (text: string) => void;
  onClose: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  // Answers of earlier requests must not overwrite a newer one.
  const request = useRef(0);
  const [instruction, setInstruction] = useState("");
  const [state, setState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [result, setResult] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    input.current?.focus();
  }, []);

  async function run(text: string) {
    const instructionText = text.trim();
    if (!instructionText) return;
    const id = ++request.current;
    setState("loading");
    setError("");
    try {
      const rewritten = await api.rewrite(target.text, instructionText, target.context);
      if (id !== request.current) return;
      setResult(rewritten);
      setState("done");
    } catch (e) {
      if (id !== request.current) return;
      setError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
      setState("error");
    }
  }

  return (
    <div
      role="dialog"
      aria-label="Edit selection with AI"
      className="te-pop w-[26rem] max-w-[calc(100vw-1.5rem)] overflow-hidden rounded-xl bg-white text-sm text-[var(--ink)] shadow-[0_0_0_1px_rgba(26,32,51,0.1),0_20px_44px_-12px_rgba(26,32,51,0.35)]"
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
    >
      <form
        className="flex items-center gap-2 border-b border-[var(--rule)] px-3 py-2.5"
        onSubmit={(e) => {
          e.preventDefault();
          void run(instruction);
        }}
      >
        <span className="text-[var(--accent)]">
          <SparkIcon />
        </span>
        <input
          ref={input}
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="Tell the AI what to change…"
          className="min-w-0 flex-1 bg-transparent py-1 outline-none placeholder:text-[var(--ink-soft)]/70"
          aria-label="Instruction"
        />
        <button
          type="submit"
          disabled={!instruction.trim() || state === "loading"}
          className="rounded-md bg-[var(--accent)] px-2.5 py-1 text-xs font-medium text-white transition hover:brightness-110 disabled:opacity-40"
        >
          {state === "done" || state === "error" ? "Try again" : "Rewrite"}
        </button>
        <button type="button" onClick={onClose} aria-label="Close" className="rounded p-1 text-[var(--ink-soft)] hover:bg-wash">
          <CloseIcon />
        </button>
      </form>

      {state === "idle" && (
        <div className="flex flex-wrap gap-1.5 px-3 py-3">
          {PRESETS.map((preset) => (
            <button
              key={preset}
              type="button"
              onClick={() => {
                setInstruction(preset);
                void run(preset);
              }}
              className="rounded-full bg-[#eef0f8] px-3 py-1 text-xs text-[var(--ink)] transition hover:bg-[#e1e5f5]"
            >
              {preset}
            </button>
          ))}
        </div>
      )}

      {state === "loading" && (
        <div className="space-y-2 px-4 py-4" role="status" aria-label="Rewriting">
          <div className="te-shimmer h-3 w-11/12 rounded" />
          <div className="te-shimmer h-3 w-full rounded" />
          <div className="te-shimmer h-3 w-2/3 rounded" />
        </div>
      )}

      {state === "error" && (
        <p role="alert" className="px-4 py-3 text-[var(--bad-ink)]">
          {error}
        </p>
      )}

      {state === "done" && (
        <div className="px-4 py-3">
          <p className="mb-1.5 text-xs font-medium text-[var(--ink-soft)]">Suggestion</p>
          <p className="max-h-56 overflow-auto whitespace-pre-wrap rounded-lg bg-[#f4f6fc] px-3 py-2.5 leading-relaxed">{result}</p>
          <div className="mt-3 flex items-center justify-end gap-2">
            <button type="button" onClick={onClose} className="rounded-md px-3 py-1.5 text-[var(--ink-soft)] transition hover:bg-wash">
              Discard
            </button>
            <button
              type="button"
              onClick={() => onApply(result)}
              className="rounded-md bg-[var(--ink)] px-3 py-1.5 font-medium text-white transition hover:bg-[#2b3350]"
            >
              Replace selection
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
