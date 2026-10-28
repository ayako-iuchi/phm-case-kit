#!/usr/bin/env python3
"""termcount — count where a term occurs in a source, page by page.

Usage:
    termcount.py SOURCE.txt TERM [TERM ...] [--pages A-B] [--ignore-case]

SOURCE.txt is your own `pdftotext -layout` extract (see quotecheck.py).
Whitespace is removed from both the source and the term before counting, so
a term broken across two lines is still found ("Predictive" at the end of one
line and "Maintenance" at the start of the next). The cost: a term can also
match across a word boundary that whitespace used to mark.

Overlapping occurrences are counted ("aa" occurs 3 times in "aaaa"). A
term that runs across a page break is not counted.

A count of 0 means only this: the term does not occur in the text extracted
from these pages. It says nothing about images, about pages outside the
range, about other documents, or about what the author of the source says
elsewhere.

Exit status: 0, or 2 on bad input.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pages import norm, read_pages, page_texts, parse_range  # noqa: E402
from quotecheck import NOTE_FOOTER  # noqa: E402


def count(texts, term, first, last, ignore_case=False):
    t = norm(term)
    if not t:
        raise ValueError("empty term")
    if ignore_case:
        t = t.casefold()
    hits = {}
    for p in range(first, last + 1):
        page = texts[p - 1].casefold() if ignore_case else texts[p - 1]
        c, start = 0, 0
        while True:
            i = page.find(t, start)
            if i < 0:
                break
            c += 1
            start = i + 1
        if c:
            hits[p] = c
    return hits


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("source")
    ap.add_argument("terms", nargs="+")
    ap.add_argument("--pages", default=None, help="page range, e.g. 1-119 (default: all)")
    ap.add_argument("--ignore-case", action="store_true")
    ap.add_argument("--header-lines", type=int, default=1)
    ap.add_argument("--note-footer", action="store_true")
    args = ap.parse_args(argv)
    try:
        pages = read_pages(args.source, args.header_lines, NOTE_FOOTER if args.note_footer else None)
        texts = page_texts(pages)
        first, last = parse_range(args.pages, len(texts))
        print(f"pages {first}-{last} of {len(texts)}" + (" (case ignored)" if args.ignore_case else ""))
        for term in args.terms:
            hits = count(texts, term, first, last, args.ignore_case)
            total = sum(hits.values())
            where = ", ".join(f"p.{p}" + (f" x{c}" if c > 1 else "") for p, c in hits.items())
            print(f"{term}\t{total}\t{where if where else 'not in the extracted text of these pages'}")
    except (OSError, ValueError) as e:
        print(f"termcount: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
