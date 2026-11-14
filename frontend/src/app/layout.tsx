import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Document data extractor",
  description: "Extract data from documents with cited sources and fill Word templates.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">
        <header className="border-b border-zinc-200 bg-white">
          <nav className="mx-auto flex max-w-5xl items-center gap-6 px-6 py-3 text-sm">
            <Link href="/" className="font-semibold text-zinc-900">
              Data extractor
            </Link>
            <Link href="/" className="text-zinc-600 hover:text-zinc-900">
              Documents
            </Link>
            <Link href="/templates" className="text-zinc-600 hover:text-zinc-900">
              Templates
            </Link>
          </nav>
        </header>
        <main className="mx-auto max-w-5xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
