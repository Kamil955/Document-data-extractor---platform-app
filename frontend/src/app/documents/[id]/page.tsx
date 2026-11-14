import { Suspense } from "react";
import { ExtractView } from "@/components/extract-view";

export default function ExtractPage() {
  // The client component reads the route params in the browser, so it sits in a Suspense
  // boundary (required for dynamic routes with Cache Components).
  return (
    <Suspense>
      <ExtractView />
    </Suspense>
  );
}
