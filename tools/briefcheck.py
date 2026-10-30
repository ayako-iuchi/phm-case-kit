#!/usr/bin/env python3
"""briefcheck — check that every line of a one-page brief shows its source.

Usage:
    briefcheck.py BRIEF.md [--max-chars N] [--quiet]

A one-page brief for executives is short, and every number and quotation in
it is something a reader may repeat. This tool reads a brief written in
Markdown whose last section is a numbered list of sources (a heading named
出典 or Sources, then "1. ...", "2. ..."), with source numbers cited in the
text as [1], [2, 3] or ［1］. It checks the brief's form, not its facts: it
cannot open a source.

Checks (each makes the exit status 1):
    B1  a line with a number or a quotation (「」, 『』 or "") cites no source
    B2  a line cites a source number that is not in the list
    B3  a source in the list is never cited
    B4  a line cites a source marked fictional (架空 or fictional in the
        source's entry) but does not say 架空 or fictional itself
    B5  a source's entry gives no date (2026年10月30日, 2026年10月,
        2026-10-30, 30 October 2026 or October 2026)
    B6  the text before the sources is longer than --max-chars characters
        (default 1600, about one printed page of Japanese), not counting
        spaces and Markdown marks

Lines checked are every non-empty line before the sources heading except
headings (#), the title, horizontal rules and HTML comments. In B1, a date followed by 時点
or preceded by "as of" is not counted as a number, and neither are the
digits of a citation itself ([1]). A line counts as citing a source if it
contains a marker; a marker covers its whole line.

Exit status: 0 if no check fires, 1 if any does, 2 on bad input.
"""
import argparse
import re
import sys

SOURCES_HEADING = re.compile(r"^#{1,6}\s*(出典|Sources)\s*$")
HEADING = re.compile(r"^#{1,6}\s")
ITEM = re.compile(r"^\s*(\d+)\.\s+(.*\S)\s*$")
MARKER = re.compile(r"[\[［]\s*(\d+(?:\s*[,，、]\s*\d+)*)\s*[\]］]")
ASOF = re.compile(r"(\d{4}年\d{1,2}月(?:\d{1,2}日)?\s*時点|as of\s+(?:\d{1,2}\s+)?[A-Z][a-z]+\s+\d{4}"
                  r"|as of\s+\d{4}-\d{2}(?:-\d{2})?)", re.I)
DATE = re.compile(r"(\d{4}年\d{1,2}月(\d{1,2}日)?|\d{4}-\d{2}(-\d{2})?"
                  r"|(\d{1,2}\s+)?(January|February|March|April|May|June|July|August|September|October"
                  r"|November|December)\s+\d{4})")
QUOTE = re.compile(r"[「『“\"]")
FICTION = re.compile(r"架空|fictional", re.I)


def parse(text):
    """Return (lines, sources): lines = [(lineno, text)], sources = {n: (lineno, entry)}."""
    lines, sources, in_sources, title_seen = [], {}, False, False
    text = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    for n, raw in enumerate(text.splitlines(), start=1):
        s = raw.strip()
        if SOURCES_HEADING.match(s):
            in_sources = True
            continue
        if in_sources:
            if HEADING.match(s):
                in_sources = False
                continue
            m = ITEM.match(raw)
            if m:
                k = int(m.group(1))
                if k in sources:
                    raise ValueError(f"line {n}: source {k} is listed twice")
                sources[k] = (n, m.group(2))
            continue
        if not s or HEADING.match(s) or re.fullmatch(r"[-*_]{3,}", s):
            title_seen = title_seen or s.startswith("# ")
            continue
        if sources:
            continue
        lines.append((n, s))
    if not sources:
        raise ValueError("no numbered list of sources under a heading named 出典 or Sources")
    return lines, sources


def cited(line):
    out = []
    for m in MARKER.finditer(line):
        out.extend(int(x) for x in re.split(r"\s*[,，、]\s*", m.group(1)))
    return out


def check(text, max_chars=1600):
    lines, sources = parse(text)
    issues, used = [], set()
    body_chars = 0
    for n, s in lines:
        refs = cited(s)
        used.update(refs)
        plain = MARKER.sub("", ASOF.sub("", s))
        body_chars += len(re.sub(r"[\s*_`>#\-|]", "", MARKER.sub("", s)))
        if not refs and (re.search(r"\d", plain) or QUOTE.search(plain)):
            issues.append((n, "B1", f"a number or quotation with no source: {s[:50]}"))
        for k in refs:
            if k not in sources:
                issues.append((n, "B2", f"cites [{k}], which is not in the sources"))
        if any(k in sources and FICTION.search(sources[k][1]) for k in refs) and not FICTION.search(s):
            issues.append((n, "B4", f"cites a fictional source but does not say so: {s[:50]}"))
    for k, (n, entry) in sorted(sources.items()):
        if k not in used:
            issues.append((n, "B3", f"source {k} is never cited"))
        if not DATE.search(entry):
            issues.append((n, "B5", f"source {k} gives no date"))
    if body_chars > max_chars:
        issues.append((0, "B6", f"the brief is {body_chars} characters before its sources (limit {max_chars})"))
    return lines, sources, issues


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("brief")
    ap.add_argument("--max-chars", type=int, default=1600)
    ap.add_argument("--quiet", action="store_true", help="print only the summary")
    args = ap.parse_args(argv)
    try:
        if args.max_chars < 1:
            raise ValueError("--max-chars must be 1 or more")
        with open(args.brief, encoding="utf-8-sig") as f:
            text = f.read()
        lines, sources, issues = check(text, args.max_chars)
    except (OSError, ValueError, UnicodeDecodeError) as e:
        print(f"briefcheck: {args.brief}: {e}", file=sys.stderr)
        return 2
    if not args.quiet:
        for n, code, msg in sorted(issues):
            print(f"{code}\tline {n}\t{msg}")
    with_refs = sum(1 for _, s in lines if cited(s))
    print(f"lines: {len(lines)}  with a source: {with_refs}")
    print(f"sources: {len(sources)}")
    codes = [c for _, c, _ in issues]
    print("issues: " + "  ".join(f"{c} {codes.count(c)}" for c in ("B1", "B2", "B3", "B4", "B5", "B6")))
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
