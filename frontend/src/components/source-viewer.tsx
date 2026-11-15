"use client";

import type { PDFDocumentProxy } from "pdfjs-dist";
import type { TextItem, TextMarkedContent } from "pdfjs-dist/types/src/display/api";
import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { locateQuote } from "@/lib/locate-quote";
import type { Citation } from "@/lib/types";
import { ErrorBox, Spinner, secondaryButtonClass } from "./ui";

// The original document next to the extracted value: a PDF page with the quote highlighted, or
// (for Word files, which have no pages) the cited passage as text. Opens from a citation.

type PdfJs = typeof import("pdfjs-dist");

let pdfjsPromise: Promise<PdfJs> | null = null;
// pdf.js touches browser-only globals when it is imported, so it is loaded on demand in the
// browser, never while Next.js renders the page on the server.
function loadPdfJs(): Promise<PdfJs> {
  pdfjsPromise ??= import("pdfjs-dist").then((pdfjs) => {
    // The parsing runs in a Web Worker, so a big PDF does not freeze the page.
    pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();
    return pdfjs;
  });
  return pdfjsPromise;
}

// One download per document, however many citations are opened.
const pdfCache = new Map<string, Promise<PDFDocumentProxy>>();
function loadPdf(documentId: string): Promise<PDFDocumentProxy> {
  let pending = pdfCache.get(documentId);
  if (!pending) {
    pending = Promise.all([loadPdfJs(), api.downloadDocument(documentId)]).then(([pdfjs, data]) =>
      pdfjs.getDocument({ data }).promise,
    );
    pdfCache.set(documentId, pending);
    pending.catch(() => pdfCache.delete(documentId)); // do not cache a failure
  }
  return pending;
}

interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}

interface Rendered {
  page: number;
  boxes: Box[];
  match: "exact" | "partial" | "none";
}

// Items of a text layer that carry text (the others are markers for structure).
const isTextItem = (item: TextItem | TextMarkedContent): item is TextItem => "str" in item;

function PdfSource({ citation }: { citation: Citation }) {
  const { document_id: documentId, quote } = citation;
  const firstPage = citation.page_start ?? 1;
  const lastPage = citation.page_end ?? firstPage;

  const canvas = useRef<HTMLCanvasElement>(null);
  const holder = useRef<HTMLDivElement>(null);
  const firstBox = useRef<HTMLDivElement>(null);
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [pageNumber, setPageNumber] = useState(firstPage);
  const [rendered, setRendered] = useState<Rendered | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadPdf(documentId)
      .then(async (loaded) => {
        // A quote may continue on the next page: open the page where it is found whole, or else
        // the first page where at least a part of it is.
        let partial: number | null = null;
        for (let n = firstPage; n <= Math.min(lastPage, loaded.numPages); n++) {
          const content = await (await loaded.getPage(n)).getTextContent();
          const found = locateQuote(content.items.filter(isTextItem).map((i) => i.str), quote);
          if (found?.exact) {
            setPageNumber(n);
            break;
          }
          if (found && partial === null) partial = n;
          if (n === Math.min(lastPage, loaded.numPages) && partial !== null) setPageNumber(partial);
        }
        setPdf(loaded);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not open the PDF"));
  }, [documentId, quote, firstPage, lastPage]);

  useEffect(() => {
    if (!pdf || !canvas.current || !holder.current) return;
    const target = canvas.current;
    const width = holder.current.clientWidth;
    let task: { cancel: () => void; promise: Promise<unknown> } | null = null;
    let cancelled = false;

    (async () => {
      const pdfjs = await loadPdfJs();
      const page = await pdf.getPage(pageNumber);
      // Fit the page to the width of the panel. The canvas gets more pixels than CSS pixels on
      // sharp screens (devicePixelRatio), otherwise the text looks blurry.
      const scale = width / page.getViewport({ scale: 1 }).width;
      const viewport = page.getViewport({ scale });
      const ratio = window.devicePixelRatio || 1;
      target.width = Math.floor(viewport.width * ratio);
      target.height = Math.floor(viewport.height * ratio);
      target.style.width = `${viewport.width}px`;
      target.style.height = `${viewport.height}px`;
      task = page.render({ canvas: target, viewport: page.getViewport({ scale: scale * ratio }) });
      await task.promise;

      const content = await page.getTextContent();
      const items = content.items.filter(isTextItem);
      const found = locateQuote(items.map((i) => i.str), quote);

      // Where a character starts inside an item. Letters have different widths ("i" vs "m"), so
      // counting characters would drift; measuring the text in the item's own font does not.
      // Only proportions matter, so the font size used for measuring is arbitrary.
      const ruler = window.document.createElement("canvas").getContext("2d");
      const share = (item: TextItem, chars: number): number => {
        if (ruler) {
          ruler.font = `100px ${content.styles[item.fontName]?.fontFamily ?? "sans-serif"}`;
          const whole = ruler.measureText(item.str).width;
          if (whole > 0) return ruler.measureText(item.str.slice(0, chars)).width / whole;
        }
        return chars / Math.max(item.str.length, 1);
      };

      const boxes: Box[] = (found?.ranges ?? []).map(({ item, start, end }) => {
        const part = items[item];
        // Position of the item's baseline start in viewport pixels (y grows downwards there).
        const [, , , , x, y] = pdfjs.Util.transform(viewport.transform, part.transform);
        const itemWidth = part.width * scale;
        const itemHeight = part.height * scale;
        const left = x + share(part, start) * itemWidth;
        return {
          left,
          top: y - itemHeight,
          width: x + share(part, end) * itemWidth - left,
          height: itemHeight * 1.2, // a little below the baseline, for letters like "g"
        };
      });
      if (!cancelled)
        setRendered({ page: pageNumber, boxes, match: !found ? "none" : found.exact ? "exact" : "partial" });
    })().catch((e) => {
      // Cancelling a render that is no longer needed is expected, not an error.
      if (!cancelled && e?.name !== "RenderingCancelledException") setError("Could not draw the page");
    });

    return () => {
      cancelled = true;
      task?.cancel();
    };
  }, [pdf, pageNumber, quote]);

  // Bring the highlight into view: on a long page it can be far below the fold.
  const ready = rendered?.page === pageNumber ? rendered : null;
  useEffect(() => {
    firstBox.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [ready]);

  if (error) return <ErrorBox>{error}</ErrorBox>;

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-2 text-sm">
        <button
          className={secondaryButtonClass}
          disabled={pageNumber <= 1}
          onClick={() => setPageNumber((n) => n - 1)}
          aria-label="Previous page"
        >
          ←
        </button>
        <span className="text-ink-soft">
          Page {pageNumber}
          {pdf && ` of ${pdf.numPages}`}
        </span>
        <button
          className={secondaryButtonClass}
          disabled={!pdf || pageNumber >= pdf.numPages}
          onClick={() => setPageNumber((n) => n + 1)}
          aria-label="Next page"
        >
          →
        </button>
      </div>

      {ready?.match === "partial" && (
        <p className="mb-2 text-xs text-warn">
          Only a part of the quote is highlighted: it probably continues on the neighbouring page.
        </p>
      )}
      {ready?.match === "none" && (
        <p className="mb-2 text-xs text-warn">
          The quote was not found as text on this page (the PDF&apos;s text can differ from what the model read).
          Read the page yourself.
        </p>
      )}

      <div ref={holder} className="relative w-full overflow-hidden rounded-md bg-white shadow ring-1 ring-rule">
        <canvas ref={canvas} className="block" />
        {/* Highlights sit on top of the canvas; mix-blend-multiply keeps the text readable. */}
        {ready?.boxes.map((box, i) => (
          <div
            key={i}
            ref={i === 0 ? firstBox : undefined}
            className="pointer-events-none absolute rounded-sm bg-yellow-300/60 mix-blend-multiply"
            style={box}
          />
        ))}
        {!ready && (
          <div className="absolute inset-0 flex items-start justify-center bg-white/70 pt-10">
            <Spinner label="Drawing the page…" />
          </div>
        )}
      </div>
    </div>
  );
}

// Word files have no pages, so the cited passage is shown as text with the quote marked.
function TextSource({ citation }: { citation: Citation }) {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listChunks(citation.document_id)
      .then((chunks) => {
        const chunk = chunks.find((c) => c.id === citation.chunk_id);
        if (chunk) setText(chunk.text);
        else setError("The cited passage no longer exists (the document was processed again).");
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Unexpected error"));
  }, [citation.document_id, citation.chunk_id]);

  if (error) return <ErrorBox>{error}</ErrorBox>;
  if (text === null) return <Spinner label="Loading…" />;

  const range = locateQuote([text], citation.quote)?.ranges[0];
  const start = range?.start ?? 0;
  const end = range?.end ?? 0;

  return (
    <div>
      <p className="mb-2 text-xs text-ink-soft">
        This file has no pages. The passage the model was given, with the quote marked:
      </p>
      <p className="whitespace-pre-wrap rounded-md bg-white p-4 text-sm leading-relaxed text-ink shadow ring-1 ring-rule">
        {range ? (
          <>
            {text.slice(0, start)}
            <mark className="rounded-sm bg-yellow-300/70">{text.slice(start, end)}</mark>
            {text.slice(end)}
          </>
        ) : (
          text
        )}
      </p>
    </div>
  );
}

export function SourceViewer({ citation, onClose }: { citation: Citation | null; onClose: () => void }) {
  useEffect(() => {
    if (!citation) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [citation, onClose]);

  if (!citation) return null;
  // A page number means a PDF (only PDFs have pages).
  const isPdf = citation.page_start !== null;

  return (
    <aside
      className="fixed inset-y-0 right-0 z-40 flex w-full flex-col bg-wash shadow-2xl ring-1 ring-rule sm:w-[min(46rem,55vw)]"
      aria-label="Source document"
    >
      <header className="flex items-start justify-between gap-3 border-b border-rule bg-white px-4 py-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-ink">{citation.filename}</p>
          {citation.section_path && <p className="truncate text-xs text-ink-soft">{citation.section_path}</p>}
        </div>
        <button className={secondaryButtonClass} onClick={onClose}>
          Close
        </button>
      </header>
      <div className="border-b border-rule bg-white px-4 py-2 text-sm text-ink">“{citation.quote}”</div>
      <div className="flex-1 overflow-y-auto p-4">
        {/* key: a different citation starts a fresh viewer instead of reusing the old state */}
        {isPdf ? (
          <PdfSource key={`${citation.chunk_id}:${citation.quote}`} citation={citation} />
        ) : (
          <TextSource key={citation.chunk_id} citation={citation} />
        )}
      </div>
    </aside>
  );
}
