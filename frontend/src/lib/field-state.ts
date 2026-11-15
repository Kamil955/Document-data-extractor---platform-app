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

// The colour family of each state (see Tone in components/ui.tsx).
export const STATE_TONE: Record<FieldState, "ok" | "info" | "warn" | "neutral" | "bad"> = {
  verified: "ok",
  edited: "info",
  check: "warn",
  missing: "neutral",
  error: "bad",
};
