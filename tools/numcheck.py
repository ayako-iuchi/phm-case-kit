#!/usr/bin/env python3
"""numcheck — check a number register: the same number, the same thing?

Usage:
    numcheck.py REGISTER.tsv [--text DOC=PATH ...] [--header-lines N]
                [--note-footer] [--strict] [--quiet]

A set of documents derived from one source (a proposal, a business plan, a
requirements document, explanatory posts) repeats the same numbers. The value
can stay the same while what it measures changes: a reduction in stoppage
time becomes a count, a share of something else, or a rate applied to money.
The register has one row per occurrence of a number and records what that
document says the number measures. This tool groups the rows and reports:

    DRIFT     one value, more than one definition (measures, unit or base)
    CONFLICT  one definition (measures, unit and base), more than one value

These are findings for a person to judge, not errors: two definitions of one
value may be two different things that happen to share a number. With
--strict they also make the exit status 1.

With --text DOC=PATH (a pdftotext extract with form feeds between pages, one
per document), it also checks the register against the text:

    QUOTE     the row's quote is not on the page given (all whitespace
              removed from both, as in quotecheck)
    MISSED    a page has more occurrences of a value than the register has
              rows for that value, document and page

MISSED counts a value as its number and suffix with nothing but optional
brackets between them ("82%", "[82]%", "［82］％"); full-width digits and
signs are read as half-width, and a digit, comma or point just before or
just after does not count ("182%" is not "82%"). Several documents compiled
in one file can share it (--text '#17.2=all.txt' --text '#17.3=all.txt'); a
page of that file is then counted against the rows of all of them. It is a
check on the
register's completeness for the documents you pass: it searches them for
every value that a row of one of those documents has, so pass only documents
you meant to inventory in full. Rows of documents without a --text are not
checked against any text; a row with an empty quote is not quote-checked.

Columns (tab-separated, header row required, other columns ignored):
    id           unique id
    value        the number as written, normalized ("82%", "1.5年", "3.2億円")
    document     document id (matches DOC in --text)
    page         page number in that document's text (1 = before the first \\f)
    quote        a short quote that contains the value ("" to skip)
    measures     what the document says the value measures
    unit         unit of the measured thing (time, count, money, share, ...)
    base         what it is a share of, or "-"
    period       period or scope, or "-"
    placeholder  yes if marked as a placeholder (e.g. [82]), else no
    note         anything else

Exit status: 0 if no check fires, 1 if QUOTE or MISSED fires (or DRIFT or
CONFLICT with --strict), 2 on bad input.
"""
import argparse
import csv
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pages import norm, read_pages, page_texts  # noqa: E402

REQUIRED = ["id", "value", "document", "page", "quote", "measures", "unit",
            "base", "period", "placeholder", "note"]
FULLWIDTH = str.maketrans("０１２３４５６７８９．，％〜［］－", "0123456789.,%~[]-")
NOTE_FOOTER = r"^https?://note\.com/"


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        try:
            header = next(reader, None)
            if header is None:
                raise ValueError(f"{path}: empty file")
            dups = sorted({c for c in header if header.count(c) > 1})
            if dups:
                raise ValueError(f"{path}: header names {', '.join(dups)} more than once")
            missing = [c for c in REQUIRED if c not in header]
            if missing:
                raise ValueError(f"{path}: header lacks {', '.join(missing)}")
            rows, seen = [], {}
            for n, fields in enumerate(reader, start=2):
                if not any(x.strip() for x in fields):
                    continue
                if len(fields) != len(header):
                    raise ValueError(f"{path}:{n}: {len(fields)} fields, header has {len(header)}")
                r = {k: v.strip() for k, v in zip(header, fields)}
                for k in ("id", "value", "document", "page", "measures"):
                    if not r[k]:
                        raise ValueError(f"{path}:{n}: {k} is empty")
                if not r["page"].isdigit() or int(r["page"]) < 1:
                    raise ValueError(f"{path}:{n}: page {r['page']!r} is not a page number")
                if r["placeholder"] not in ("yes", "no"):
                    raise ValueError(f"{path}:{n}: placeholder must be yes or no")
                if r["id"] in seen:
                    raise ValueError(f"{path}:{n}: id {r['id']} also on line {seen[r['id']]}")
                seen[r["id"]] = n
                if split_value(r["value"]) is None:
                    raise ValueError(f"{path}:{n}: value {r['value']!r} does not start with a number")
                r["_line"] = n
                rows.append(r)
        except csv.Error as e:
            raise ValueError(f"{path}: {e}")
    if not rows:
        raise ValueError(f"{path}: no rows")
    return rows


def split_value(value):
    """'82%' -> ('82', '%'); '8~12回' -> ('8~12', '回'); None if no leading number."""
    v = norm(value).translate(FULLWIDTH)
    m = re.fullmatch(r"(\d[\d.,]*(?:[~\-–]\d[\d.,]*)?)(.*)", v)
    return (m.group(1), m.group(2)) if m else None


def value_pattern(value):
    num, suffix = split_value(value)
    return re.compile(r"(?<![\d.,])\[?" + re.escape(num) + r"\]?" + re.escape(suffix) +
                      (r"(?![\d])" if not suffix else ""))


def definition(r):
    return (r["measures"], r["unit"], r["base"])


def findings(rows):
    by_value, by_def = defaultdict(list), defaultdict(list)
    for r in rows:
        key = "".join(split_value(r["value"]))
        by_value[key].append(r)
        by_def[definition(r)].append(r)
    drift = {v: rs for v, rs in by_value.items() if len({definition(r) for r in rs}) > 1}
    conflict = {d: rs for d, rs in by_def.items() if len({"".join(split_value(r["value"])) for r in rs}) > 1}
    return by_value, drift, conflict


def text_checks(rows, texts, doc_path=None):
    """texts: {doc: [normalized page text, ...]}; doc_path: {doc: path}, so that several
    documents compiled in one file are counted together. Returns (code, row or None, message)."""
    issues = []
    doc_path = doc_path or {d: d for d in texts}
    for r in rows:
        pages = texts.get(r["document"])
        if pages is None:
            continue
        p = int(r["page"])
        if p > len(pages):
            issues.append(("QUOTE", r, f"page {p} is past the end ({len(pages)} pages)"))
            continue
        if r["quote"] and norm(r["quote"]) not in pages[p - 1]:
            issues.append(("QUOTE", r, f"quote not on p.{p}"))
    counts = defaultdict(int)
    for r in rows:
        if r["document"] in doc_path:
            counts[(doc_path[r["document"]], int(r["page"]), "".join(split_value(r["value"])))] += 1
    values = {}
    for r in rows:
        if r["document"] in texts:  # values from documents without a text are not searched for
            values.setdefault("".join(split_value(r["value"])), r["value"])
    done = set()
    for doc, pages in texts.items():
        path = doc_path[doc]
        if path in done:
            continue
        done.add(path)
        name = "+".join(sorted(d for d in texts if doc_path[d] == path))
        for key, value in values.items():
            pat = value_pattern(value)
            for i, t in enumerate(pages, start=1):
                n = len(pat.findall(t.translate(FULLWIDTH)))
                have = counts.get((path, i, key), 0)
                if n > have:
                    issues.append(("MISSED", None, f"{name} p.{i}: {value} occurs {n} times, register has {have}"))
    return issues


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("register")
    ap.add_argument("--text", action="append", default=[], metavar="DOC=PATH",
                    help="a document's text, to check quotes and missed occurrences")
    ap.add_argument("--header-lines", type=int, default=0,
                    help="lines dropped from the top of every page (default 0)")
    ap.add_argument("--note-footer", action="store_true", help="drop lines that start with a note.com URL")
    ap.add_argument("--strict", action="store_true", help="DRIFT and CONFLICT also make the exit status 1")
    ap.add_argument("--quiet", action="store_true", help="print only the summary")
    args = ap.parse_args(argv)
    try:
        rows = load(args.register)
        texts, doc_path, cache = {}, {}, {}
        for spec in args.text:
            doc, sep, path = spec.partition("=")
            if not sep or not doc or not path:
                raise ValueError(f"--text {spec!r} is not DOC=PATH")
            if doc in texts:
                raise ValueError(f"--text names {doc} twice")
            key = os.path.realpath(path)
            if key not in cache:
                pages = read_pages(path, header_lines=args.header_lines,
                                   drop_line_regex=NOTE_FOOTER if args.note_footer else None)
                cache[key] = page_texts(pages)
            texts[doc], doc_path[doc] = cache[key], key
    except (OSError, ValueError, UnicodeDecodeError) as e:
        print(f"numcheck: {e}", file=sys.stderr)
        return 2
    by_value, drift, conflict = findings(rows)
    issues = text_checks(rows, texts, doc_path)
    if not args.quiet:
        for v, rs in sorted(drift.items()):
            defs = sorted({definition(r) for r in rs})
            print(f"DRIFT\t{rs[0]['value']}\t{len(defs)} definitions in {len(rs)} rows")
            for d in defs:
                ids = ",".join(r["id"] for r in rs if definition(r) == d)
                print(f"\t\tmeasures={d[0]} | unit={d[1]} | base={d[2]}\t{ids}")
        for d, rs in sorted(conflict.items()):
            vals = sorted({r["value"] for r in rs})
            print(f"CONFLICT\tmeasures={d[0]} | unit={d[1]} | base={d[2]}\tvalues {', '.join(vals)}\t"
                  + ",".join(r["id"] for r in rs))
        for code, r, msg in issues:
            where = f"line {r['_line']}\tid {r['id']}\t" if r else ""
            print(f"{code}\t{where}{msg}")
    docs = sorted({r["document"] for r in rows})
    print(f"rows: {len(rows)}  values: {len(by_value)}  documents: {len(docs)}")
    print(f"drift: {len(drift)}  conflict: {len(conflict)}")
    print(f"quote: {sum(c == 'QUOTE' for c, _, _ in issues)}  missed: {sum(c == 'MISSED' for c, _, _ in issues)}"
          f"  (texts: {len(set(doc_path.values()))} files, {len(texts)} documents)")
    bad = bool(issues) or (args.strict and (drift or conflict))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
