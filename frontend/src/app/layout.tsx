import type { Metadata } from "next";
import { Suspense } from "react";
import { SiteNav } from "@/components/site-nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "Document data extractor",
  description: "Extract data from documents with cited sources and fill Word templates.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">
        {/* usePathname (the active link) is known only at request time: stream it in. */}
        <Suspense fallback={<div className="h-14 border-b border-rule bg-white" />}>
          <SiteNav />
        </Suspense>
        <main className="mx-auto max-w-5xl px-6 py-10">{children}</main>
      </body>
    </html>
  );
}
