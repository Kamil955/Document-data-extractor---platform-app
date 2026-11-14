import { Suspense } from "react";
import { ExtractionView } from "@/components/extraction-view";

export default function ExtractionPage() {
  return (
    <Suspense>
      <ExtractionView />
    </Suspense>
  );
}
