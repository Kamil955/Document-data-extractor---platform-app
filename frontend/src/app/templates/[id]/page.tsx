import { Suspense } from "react";
import { TemplateDetail } from "@/components/template-detail";

// useParams in the client component needs a Suspense boundary (cacheComponents).
export default function TemplatePage() {
  return (
    <Suspense>
      <TemplateDetail />
    </Suspense>
  );
}
