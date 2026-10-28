"""pages — read a pdftotext extract as pages, and normalize text for matching.

Shared by quotecheck.py and termcount.py. Standard library only.

A page is the text between two form feeds (\\f), as `pdftotext` writes them.
Pages are numbered from 1. A trailing empty page after the last form feed is
dropped.

Normalization removes every whitespace character (str.isspace(): spaces,
tabs, line breaks, the ideographic space U+3000). Nothing else is changed: no
Unicode normalization, no case folding, no punctuation mapping. So a quotation
broken across lines by the layout still matches, while 「」 and "" or full-width
and half-width letters stay different.
"""
import re


def norm(s):
    """Remove all whitespace."""
    return "".join(ch for ch in s if not ch.isspace())


def read_pages(path, header_lines=1, drop_line_regex=None):
    """Return a list of pages, each a list of its lines (header and dropped lines removed).

    header_lines: how many lines to drop from the top of every page (a printed
        header with the time and title, for example). Leading blank lines are
        not counted as header lines.
    drop_line_regex: lines matching this regular expression (re.search on the
        line with surrounding whitespace stripped) are dropped, e.g. a footer
        URL. None drops nothing.
    """
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    chunks = raw.split("\f")
    if chunks and chunks[-1].strip() == "":
        chunks = chunks[:-1]
    pat = re.compile(drop_line_regex) if drop_line_regex else None
    pages = []
    for chunk in chunks:
        lines = chunk.splitlines()
        # drop leading blank lines, then the header lines
        i = 0
        while i < len(lines) and lines[i].strip() == "":
            i += 1
        lines = lines[i + header_lines:] if header_lines > 0 else lines[i:]
        if pat is not None:
            lines = [ln for ln in lines if not pat.search(ln.strip())]
        pages.append(lines)
    return pages


def page_texts(pages):
    """Normalized text of each page."""
    return [norm("".join(lines)) for lines in pages]


def parse_range(spec, n_pages):
    """'3-7' or '3' -> (3, 7). None -> (1, n_pages). Raises ValueError if out of range."""
    if spec is None:
        return 1, n_pages
    m = re.fullmatch(r"\s*(\d+)\s*(?:[-–]\s*(\d+))?\s*", spec)
    if not m:
        raise ValueError(f"bad page range: {spec!r}")
    a = int(m.group(1))
    b = int(m.group(2)) if m.group(2) else a
    if a < 1 or b < a or b > n_pages:
        raise ValueError(f"page range {spec!r} outside 1-{n_pages}")
    return a, b
