// "15 Nov 2026, 12:14" in the visitor's own locale.
export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
