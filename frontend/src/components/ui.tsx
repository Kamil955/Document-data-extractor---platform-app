import type { ReactNode } from "react";

export const buttonClass =
  "inline-flex items-center justify-center gap-2 rounded-md bg-zinc-900 px-3.5 py-2 text-sm font-medium text-white " +
  "shadow-sm transition hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-40";

export const secondaryButtonClass =
  "inline-flex items-center justify-center gap-2 rounded-md bg-white px-3.5 py-2 text-sm font-medium text-zinc-800 " +
  "ring-1 ring-inset ring-zinc-300 transition hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-40";

export const inputClass =
  "w-full rounded-md border-0 bg-white px-3 py-2 text-sm text-zinc-900 ring-1 ring-inset ring-zinc-300 " +
  "placeholder:text-zinc-400 focus:ring-2 focus:ring-zinc-900 focus:outline-none";

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-zinc-500" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-800" />
      {label}
    </span>
  );
}

export function ErrorBox({ children }: { children: ReactNode }) {
  return (
    <div role="alert" className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-800 ring-1 ring-red-600/20">
      {children}
    </div>
  );
}

export function Badge({ className, children }: { className: string; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${className}`}
    >
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
      className="h-2 w-full overflow-hidden rounded-full bg-zinc-200"
    >
      <div className="h-full rounded-full bg-zinc-900 transition-all duration-500" style={{ width: `${percent}%` }} />
    </div>
  );
}

export function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">{title}</h1>
      {children}
    </div>
  );
}
