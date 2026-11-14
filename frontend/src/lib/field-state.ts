import type { FieldResult } from "./types";

// One state per field, decided from the three facts the backend reports. This is the only
// place that interprets found / supported / edited, so the screen always agrees with itself.
export type FieldState = "verified" | "edited" | "check" | "missing" | "error";

export function fieldState(field: FieldResult): FieldState {
  if (field.error) return "error";
  if (!field.found) return "missing";
  if (field.edited) return "edited";
  return field.supported ? "verified" : "check";
}

export const STATE_LABEL: Record<FieldState, string> = {
  verified: "Verified",
  edited: "Confirmed by you",
  check: "Needs check",
  missing: "Not found",
  error: "Error",
};

// Tailwind classes. Written out in full (not built from pieces) so Tailwind sees them.
export const STATE_STYLE: Record<FieldState, string> = {
  verified: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  edited: "bg-sky-50 text-sky-700 ring-sky-600/20",
  check: "bg-amber-50 text-amber-800 ring-amber-600/30",
  missing: "bg-zinc-100 text-zinc-600 ring-zinc-500/20",
  error: "bg-red-50 text-red-700 ring-red-600/20",
};
