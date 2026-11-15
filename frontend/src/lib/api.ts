import type {
  Chunk,
  DocumentItem,
  Extraction,
  ExtractionSummary,
  FieldResult,
  FillReport,
  NewTemplate,
  Template,
  TemplatePreview,
} from "./types";

// Public on purpose: the browser calls the API directly (the backend allows this origin
// through CORS). Change it for a deployed backend: NEXT_PUBLIC_API_URL=https://api.example.com
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(0, `Cannot reach the API at ${API_URL}. Is the backend running?`);
  }
  if (!response.ok) {
    // FastAPI sends {"detail": "..."} (or a list of validation errors for 422).
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: { msg?: string }) => d.msg).join("; ")
          : `Request failed (${response.status})`;
    throw new ApiError(response.status, message);
  }
  return response;
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  return (await request(path, init)).json() as Promise<T>;
}

const jsonBody = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  listDocuments: () => json<DocumentItem[]>("/documents?limit=200"),

  uploadDocument(file: File) {
    const form = new FormData();
    form.append("file", file);
    return json<DocumentItem>("/documents", { method: "POST", body: form });
  },

  async deleteDocument(id: string) {
    await request(`/documents/${id}`, { method: "DELETE" });
  },

  getDocument: (id: string) => json<DocumentItem>(`/documents/${id}`),

  // The original file, for the source viewer.
  async downloadDocument(id: string): Promise<ArrayBuffer> {
    return (await request(`/documents/${id}/file`)).arrayBuffer();
  },

  listChunks: (id: string) => json<Chunk[]>(`/documents/${id}/chunks`),

  listTemplates: () => json<Template[]>("/templates"),

  createTemplate: (template: NewTemplate) => json<Template>("/templates", jsonBody("POST", template)),

  getTemplate: (id: string) => json<Template>(`/templates/${id}`),

  // Builds a template from a Word file: its {{placeholders}} become the fields.
  createTemplateFromDocx(file: File, name: string | null) {
    const form = new FormData();
    form.append("file", file);
    if (name) form.append("name", name);
    return json<Template>("/templates/from-docx", { method: "POST", body: form });
  },

  // Attaches the Word document to a template, or replaces the current one.
  putTemplateDocx(id: string, file: File) {
    const form = new FormData();
    form.append("file", file);
    return json<Template>(`/templates/${id}/docx`, { method: "PUT", body: form });
  },

  // Creates a starter document (title + a Field/Value table) from the template's fields.
  generateTemplateDocx: (id: string) => json<Template>(`/templates/${id}/docx/generate`, { method: "POST" }),

  async downloadTemplateDocx(id: string): Promise<Blob> {
    return (await request(`/templates/${id}/docx`)).blob();
  },

  getTemplatePreview: (id: string) => json<TemplatePreview>(`/templates/${id}/preview`),

  async deleteTemplate(id: string) {
    await request(`/templates/${id}`, { method: "DELETE" });
  },

  // Answers at once (202) with a "pending" extraction; the worker fills it in, so callers
  // poll getExtraction until its status is "completed" or "failed".
  extract: (documentId: string, templateId: string) =>
    json<Extraction>(`/documents/${documentId}/extract`, jsonBody("POST", { template_id: templateId })),

  getExtraction: (id: string) => json<Extraction>(`/extractions/${id}`),

  listExtractions: (documentId: string) =>
    json<ExtractionSummary[]>(`/documents/${documentId}/extractions`),

  correctValue: (extractionId: string, key: string, value: string) =>
    json<FieldResult>(`/extractions/${extractionId}/values/${key}`, jsonBody("PATCH", { value })),

  async fillTemplate(
    extractionId: string,
    // Omitted: the backend fills the Word document stored with the extraction's template.
    file?: File,
  ): Promise<{ blob: Blob; filename: string; report: FillReport }> {
    const form = new FormData();
    if (file) form.append("file", file);
    const response = await request(`/extractions/${extractionId}/fill`, {
      method: "POST",
      body: form,
    });
    const list = (name: string) =>
      (response.headers.get(name) ?? "").split(",").filter(Boolean);
    // Content-Disposition: attachment; filename*=UTF-8''filled-name.docx
    const match = /filename\*=UTF-8''([^;]+)/i.exec(response.headers.get("Content-Disposition") ?? "");
    return {
      blob: await response.blob(),
      filename: match ? decodeURIComponent(match[1]) : "filled.docx",
      report: {
        filled: Number(response.headers.get("X-Fill-Filled") ?? 0),
        unverified: list("X-Fill-Unverified"),
        missing: list("X-Fill-Missing"),
        unknown: list("X-Fill-Unknown"),
      },
    };
  },
};
