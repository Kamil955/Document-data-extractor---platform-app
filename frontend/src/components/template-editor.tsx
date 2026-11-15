"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import type { Template, TemplateContent } from "@/lib/types";
import { EditorWorkspace } from "./editor/workspace";
import { ErrorBox, Spinner } from "./ui";

// Loads the template and its document, then hands over to the editor. A template without a
// document starts from an empty page: the first save creates the file.
export function TemplateEditor() {
  const { id } = useParams<{ id: string }>();
  const [loaded, setLoaded] = useState<{ template: Template; content: TemplateContent } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getTemplate(id)
      .then(async (template) => ({
        template,
        content: template.docx_filename ? await api.getTemplateContent(id) : { blocks: [], notes: [] },
      }))
      .then(setLoaded)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Unexpected error"));
  }, [id]);

  if (error) {
    return (
      <div className="mx-auto max-w-xl space-y-4 p-8">
        <ErrorBox>{error}</ErrorBox>
        <Link href={`/templates/${id}`} className="text-sm underline">
          Back to the template
        </Link>
      </div>
    );
  }
  if (!loaded) {
    return (
      <div className="p-8">
        <Spinner label="Opening the editor…" />
      </div>
    );
  }
  return <EditorWorkspace template={loaded.template} initialBlocks={loaded.content.blocks} notes={loaded.content.notes} />;
}
