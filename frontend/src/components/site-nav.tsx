"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Documents", match: (path: string) => path === "/" || path.startsWith("/documents") || path.startsWith("/extractions") },
  { href: "/templates", label: "Templates", match: (path: string) => path.startsWith("/templates") },
];

export function SiteNav() {
  const path = usePathname();
  return (
    <header className="border-b border-rule bg-white">
      <nav className="mx-auto flex h-14 max-w-5xl items-center gap-8 px-6" aria-label="Main">
        <Link href="/" className="flex items-center gap-2.5 font-semibold tracking-[-0.01em] text-ink">
          {/* A page with a verified tick: what the product does. */}
          <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden>
            <path d="M5 2.5h8.5L18 7v12.5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-16a1 1 0 0 1 1-1Z" fill="#e8ebfb" stroke="#2a3dc7" strokeWidth="1.4" strokeLinejoin="round" />
            <path d="m7.8 12.6 2.2 2.2 4.2-4.6" stroke="#2a3dc7" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Data extractor
        </Link>
        <ul className="flex h-full items-stretch gap-6 text-sm">
          {LINKS.map((link) => {
            const active = link.match(path);
            return (
              <li key={link.href} className="flex">
                <Link
                  href={link.href}
                  aria-current={active ? "page" : undefined}
                  className={`flex items-center border-b-2 pt-0.5 transition ${
                    active ? "border-accent text-ink" : "border-transparent text-ink-soft hover:text-ink"
                  }`}
                >
                  {link.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </header>
  );
}
