// Finds a quote inside the text items of one PDF page, so the viewer can highlight it.
//
// Why not a plain string search: the quote was checked against text that the BACKEND extracted
// from the PDF (pdfplumber), while the viewer gets its text from pdf.js. The two disagree about
// line breaks, spaces, hyphenation ("agree-\nment") and ligatures ("ﬁ" vs "fi"). Comparing only
// letters and digits, case-insensitively, makes all of those differences disappear.

/** A part of one text item, as character positions in its text: start..end (end excluded). */
export interface ItemRange {
  item: number;
  start: number;
  end: number;
}

export interface Location {
  ranges: ItemRange[];
  // false = only a part of the quote was found (for example a quote that continues on the next page)
  exact: boolean;
}

const KEEP = /[\p{L}\p{N}]/u;

// Letters and digits only, lowercase, ligatures expanded (NFKC). One entry per kept character,
// remembering which character of the original text it came from.
function normalize(text: string): { chars: string; origin: number[] } {
  let chars = "";
  const origin: number[] = [];
  let index = 0;
  for (const original of text) {
    for (const ch of original.normalize("NFKC").toLowerCase()) {
      if (KEEP.test(ch)) {
        chars += ch;
        origin.push(index);
      }
    }
    index += original.length;
  }
  return { chars, origin };
}

// A quote this short matches by accident (a page has many "the"), so a partial match must be
// at least this long.
const MIN_PARTIAL = 25;

function toRanges(
  items: string[],
  owners: { item: number; char: number }[],
  start: number,
  end: number, // exclusive
): ItemRange[] {
  const byItem = new Map<number, { first: number; last: number }>();
  for (let k = start; k < end; k++) {
    const { item, char } = owners[k];
    const seen = byItem.get(item);
    if (seen) seen.last = char;
    else byItem.set(item, { first: char, last: char });
  }
  // Extend over the whole word at both ends: a quote starts and ends at word boundaries, and
  // normalizing dropped punctuation, so "Washington," would otherwise lose its last letters.
  return [...byItem].map(([item, { first, last }]) => {
    const text = items[item];
    let start = first;
    let end = last + 1;
    while (start > 0 && KEEP.test(text[start - 1]) && KEEP.test(text[start])) start--;
    while (end < text.length && KEEP.test(text[end - 1]) && KEEP.test(text[end])) end++;
    return { item, start, end };
  });
}

export function locateQuote(items: string[], quote: string): Location | null {
  const wanted = normalize(quote).chars;
  if (wanted.length === 0) return null;

  // All items as one string of kept characters; owners[k] = which item/character produced it.
  let flat = "";
  const owners: { item: number; char: number }[] = [];
  items.forEach((text, item) => {
    const part = normalize(text);
    flat += part.chars;
    part.origin.forEach((char) => owners.push({ item, char }));
  });

  const exact = flat.indexOf(wanted);
  if (exact >= 0) return { ranges: toRanges(items, owners, exact, exact + wanted.length), exact: true };

  // A quote can start on this page and end on the next one (or the other way round): look for
  // its beginning, then its end, in a few decreasing lengths.
  if (wanted.length >= MIN_PARTIAL * 2) {
    for (const share of [0.75, 0.5, 0.35]) {
      const length = Math.max(MIN_PARTIAL, Math.floor(wanted.length * share));
      const head = flat.indexOf(wanted.slice(0, length));
      if (head >= 0) return { ranges: toRanges(items, owners, head, head + length), exact: false };
      const tail = flat.indexOf(wanted.slice(-length));
      if (tail >= 0) return { ranges: toRanges(items, owners, tail, tail + length), exact: false };
    }
  }
  return null;
}
