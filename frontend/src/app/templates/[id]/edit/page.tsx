import { Suspense } from "react";
import { TemplateEditor } from "@/components/template-editor";

export default function EditTemplatePage() {
  return (
    <Suspense>
      <TemplateEditor />
    </Suspense>
  );
}
