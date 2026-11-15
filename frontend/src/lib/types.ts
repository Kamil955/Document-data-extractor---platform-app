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

export interface Chunk {
  id: string;
  chunk_index: number;
  text: string;
  page_start: number | null;
  page_end: number | null;
  section_path: string | null;
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
  // Name of the template's own Word document, or null when it has none yet.
  docx_filename: string | null;
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

// pending = waiting for the worker, running = the worker is going through the fields.
export type ExtractionStatus = "pending" | "running" | "completed" | "failed";

export interface Extraction {
  extraction_id: string;
  document_id: string;
  template_id: string | null;
  model: string;
  status: ExtractionStatus;
  // Number of fields in the extraction. `results` holds the finished ones only, so
  // results.length / total is the progress while the worker is busy.
  total: number;
  results: FieldResult[];
  error: string | null;
}

export interface ExtractionSummary {
  extraction_id: string;
  template_id: string | null;
  template_name: string | null;
  model: string;
  status: ExtractionStatus;
  total: number;
  done: number;
  created_at: string;
}

export interface FillReport {
  filled: number;
  unverified: string[];
  missing: string[];
  unknown: string[];
}

// Preview of a template's Word document. The backend sends structured blocks (never HTML),
// so the browser only renders text through React and nothing from the file can inject markup.
export interface PreviewSegment {
  text: string;
  // Set when the segment is a {{placeholder}}.
  key: string | null;
  bold: boolean;
  italic: boolean;
  underline: boolean;
}

export interface PreviewParagraph {
  type: "paragraph";
  style: "normal" | "title" | "heading" | "list";
  level: number;
  segments: PreviewSegment[];
}

export interface PreviewTable {
  type: "table";
  rows: PreviewParagraph[][][];
}

export interface PlaceholderInfo {
  key: string;
  known: boolean;
}

export interface TemplatePreview {
  blocks: (PreviewParagraph | PreviewTable)[];
  placeholders: PlaceholderInfo[];
  unused_fields: string[];
  truncated: boolean;
}

// The whole document for the editor (never cut short, unlike the preview).
export interface TemplateContent {
  blocks: (PreviewParagraph | PreviewTable)[];
  // What saving would not keep (images, merged cells, ...).
  notes: string[];
}
