// Types mirror the backend schemas (backend/app/schemas.py). If a field changes there,
// change it here: TypeScript then shows every place that needs an update.

export type DocumentStatus = "uploaded" | "processing" | "indexed" | "failed";

export interface DocumentItem {
  id: string;
  filename: string;
  content_type: string;
  status: DocumentStatus;
  error: string | null;
  created_at: string;
}

export type FieldType = "text" | "number" | "date" | "boolean";

export interface TemplateField {
  key: string;
  label: string;
  description: string | null;
  type: FieldType;
}

export interface Template {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  fields: TemplateField[];
}

export interface NewTemplate {
  name: string;
  description: string | null;
  fields: TemplateField[];
}

export interface Citation {
  chunk_id: string;
  document_id: string;
  filename: string;
  page_start: number | null;
  page_end: number | null;
  section_path: string | null;
  quote: string;
  // false = the quote was NOT found in the source text: never trust it.
  verified: boolean;
}

export interface FieldResult {
  key: string;
  label: string;
  type: FieldType;
  value: string;
  found: boolean;
  supported: boolean;
  citations: Citation[];
  error: string | null;
  edited: boolean;
}

export interface Extraction {
  extraction_id: string;
  document_id: string;
  template_id: string | null;
  model: string;
  results: FieldResult[];
}

export interface FillReport {
  filled: number;
  unverified: string[];
  missing: string[];
  unknown: string[];
}
