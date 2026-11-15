import type { ReactNode } from "react";
import Link from "next/link";

// Shared building blocks. Colours come from the theme in globals.css (ink, accent, ok, warn,
// bad), so a screen never picks its own shade.

export const buttonClass =
  "inline-flex items-center justify-center gap-2 rounded-md bg-ink px-3.5 py-2 text-sm font-medium text-white " +
  "transition hover:bg-[#2b3350] disabled:cursor-not-allowed disabled:opacity-40";

export const secondaryButtonClass =
  "inline-flex items-center justify-center gap-2 rounded-md bg-white px-3.5 py-2 text-sm font-medium text-ink " +
  "ring-1 ring-inset ring-rule transition hover:bg-wash hover:ring-ink-faint disabled:cursor-not-allowed disabled:opacity-40";

export const inputClass =
  "w-full rounded-md border-0 bg-white px-3 py-2 text-sm text-ink ring-1 ring-inset ring-rule " +
  "placeholder:text-ink-faint focus:ring-2 focus:ring-accent focus:outline-none read-only:bg-wash";

// A white sheet on the desk. One border, no shadow: lists are rows inside one surface, not
// a stack of separate cards.
export const surfaceClass = "rounded-xl bg-white ring-1 ring-rule";

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-ink-soft" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-rule border-t-accent" />
      {label}
    </span>
  );
}

export function ErrorBox({ children }: { children: ReactNode }) {
  return (
    <div role="alert" className="rounded-lg bg-bad-wash px-4 py-3 text-sm text-bad ring-1 ring-bad/15">
      {children}
    </div>
  );
}

export type Tone = "ok" | "warn" | "bad" | "info" | "neutral";

// Written out in full (not built from pieces) so Tailwind finds every class.
const TONES: Record<Tone, { badge: string; dot: string }> = {
  ok: { badge: "bg-ok-wash text-ok", dot: "bg-ok" },
  warn: { badge: "bg-warn-wash text-warn", dot: "bg-[#d98a1c]" },
  bad: { badge: "bg-bad-wash text-bad", dot: "bg-bad" },
  info: { badge: "bg-accent-wash text-accent", dot: "bg-accent" },
  neutral: { badge: "bg-wash text-ink-soft", dot: "bg-ink-faint" },
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${TONES[tone].badge}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${TONES[tone].dot}`} aria-hidden />
      {children}
    </span>
  );
}

// `done` of `total` steps finished. Plain div instead of <progress>: it styles the same everywhere.
export function ProgressBar({ done, total }: { done: number; total: number }) {
  const percent = total === 0 ? 0 : Math.round((done / total) * 100);
  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={done}
      className="h-1.5 w-full overflow-hidden rounded-full bg-rule"
    >
      <div className="h-full rounded-full bg-accent transition-all duration-500" style={{ width: `${percent}%` }} />
    </div>
  );
}

export function PageHeader({
  title,
  description,
  back,
  children,
}: {
  title: string;
  // One plain sentence on what the page is for.
  description?: string;
  back?: { href: string; label: string };
  children?: ReactNode;
}) {
  return (
    <div className="mb-8">
      {back && (
        <Link href={back.href} className="mb-3 inline-flex items-center gap-1 text-sm text-ink-soft hover:text-ink">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M10 3 5 8l5 5" />
          </svg>
          {back.label}
        </Link>
      )}
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <h1 className="text-[1.65rem] leading-tight font-semibold tracking-[-0.02em] text-ink">{title}</h1>
          {description && <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-ink-soft">{description}</p>}
        </div>
        {children && <div className="flex flex-wrap items-center gap-3">{children}</div>}
      </div>
    </div>
  );
}

// Nothing here yet: say what to do next, and offer the action.
export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-ink-faint/60 px-6 py-12 text-center">
      <p className="font-medium text-ink">{title}</p>
      {children && <div className="mt-1.5 text-sm text-ink-soft">{children}</div>}
    </div>
  );
}
