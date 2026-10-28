#!/usr/bin/env python3
"""quotecheck — check that each quotation is on the page given for it.

Usage:
    quotecheck.py SOURCE.txt QUOTES.tsv [options]

SOURCE.txt is your own `pdftotext -layout` extract of the source PDF: pages
are separated by form feeds and numbered from 1. This repository never holds
source text; you supply it.

QUOTES.tsv is tab-separated with a header row. Required columns: `id`,
`page_from`, `page_to`, `quote`. Other columns are ignored. Fields are read
as they are: a double quotation mark is an ordinary character, not CSV
quoting, so a field cannot contain a tab or a line break. A byte-order mark
is allowed.

What it checks: whether the quotation, with all whitespace removed, is a
substring of the given page range, with all whitespace removed (see
tools/pages.py). That is all. A quotation that passes is on the page; whether
it is quoted in context, attributed correctly or fits the claim it supports
is not checked.

Verdict per quotation:
    OK         on the given pages
    ELSEWHERE  not on the given pages, but on other pages (listed), or across
               a page break outside them (listed as "11-12")
    MISSING    on no page and across no page break of the source

Flags (do not change the verdict; they say how much an OK is worth):
    SHORT      at most --short characters after normalization (default 10)
    MULTI      occurs on more than one page of the whole source
    DUP        the same normalized text as an earlier row
    LINE       equal to a whole line of the source page (often a heading)

--mutate adds a self-test. For every quotation that is OK and has at least 4
characters it makes four altered copies (one character replaced in the
middle, one deleted in the middle, the first character dropped, the last
character dropped) and reports how many of each the check would catch, i.e.
would not find on the given pages. Dropping the first or last character of
an OK quotation is never caught: a shortened quotation is still a substring.
That is the point of reporting it. Whether a middle change is caught depends
on the text (in "aaaa", deleting a middle "a" leaves "aaa", still on the
page), so the counts describe one run, not a guarantee. Rows that are not OK
and rows under 4 characters are left out and counted.

--evidence OUT.tsv writes one row per quotation with its id, pages, length,
verdict, flags and the pages where it occurs, and no quotation text, so the
result can be published without the source's words.

Exit status: 0 if every row is OK, 1 if any is ELSEWHERE or MISSING, 2 on
bad input (unreadable files, a bad header, page or regular expression, no
quotation rows) or when the evidence file cannot be written.
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pages import norm, read_pages, page_texts  # noqa: E402

REPLACEMENT = "〓"  # 〓 GETA MARK, used as the replaced character
NOTE_FOOTER = r"^https://note\.com/"


def load_quotes(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        need = {"id", "page_from", "page_to", "quote"}
        if reader.fieldnames is None or not need.issubset(reader.fieldnames):
            raise ValueError(f"{path}: header must include {sorted(need)}")
        rows = []
        for n, r in enumerate(reader, start=2):
            try:
                a, b = int(r["page_from"]), int(r["page_to"])
            except (TypeError, ValueError):
                raise ValueError(f"{path}:{n}: page_from/page_to must be integers")
            if a < 1 or b < a:
                raise ValueError(f"{path}:{n}: bad page range {a}-{b}")
            if not (r["quote"] or "").strip():
                raise ValueError(f"{path}:{n}: empty quote")
            rows.append({"id": r["id"], "a": a, "b": b, "quote": r["quote"]})
        if not rows:
            raise ValueError(f"{path}: no quotation rows")
        return rows


def check(texts, line_sets, rows, short=10):
    n_pages = len(texts)
    seen = {}
    results = []
    for r in rows:
        q = norm(r["quote"])
        a, b = r["a"], r["b"]
        if b > n_pages:
            raise ValueError(f"id {r['id']}: page {b} beyond the source's {n_pages} pages")
        hay = "".join(texts[a - 1:b])
        found = find_pages(texts, q)
        if q in hay:
            verdict = "OK"
            if not any(in_range(f, a, b) for f in found):
                found.append(f"{a}-{b}")  # only across the given pages' break(s)
        elif found:
            verdict = "ELSEWHERE"
        else:
            verdict = "MISSING"
        flags = []
        if len(q) <= short:
            flags.append("SHORT")
        if len(found) > 1:
            flags.append("MULTI")
        if q in seen:
            flags.append("DUP")
        else:
            seen[q] = r["id"]
        if any(q in line_sets[p - 1] for p in range(a, b + 1)):
            flags.append("LINE")
        results.append({"id": r["id"], "a": a, "b": b, "len": len(q),
                        "verdict": verdict, "flags": flags, "found": found})
    return results


def find_pages(texts, q):
    """Pages that contain q, as strings; if none, page pairs whose joined text does ("11-12")."""
    found = [str(i + 1) for i, t in enumerate(texts) if q in t]
    if not found:
        found = [f"{i + 1}-{i + 2}" for i in range(len(texts) - 1)
                 if q in texts[i] + texts[i + 1]]
    return found


def in_range(f, a, b):
    lo, _, hi = f.partition("-")
    return a <= int(lo) and int(hi or lo) <= b


def mutants(q):
    i = len(q) // 2
    sub = q[:i] + (REPLACEMENT if q[i] != REPLACEMENT else "〒") + q[i + 1:]
    return {
        "replace_middle": sub,
        "delete_middle": q[:i] + q[i + 1:],
        "drop_first": q[1:],
        "drop_last": q[:-1],
    }


def mutate(texts, rows, min_len=4):
    """Self-test on the rows whose quotation is on its given pages.

    Returns (stats, skipped) where skipped = {"not_ok": n, "short": m}.
    """
    kinds = ["replace_middle", "delete_middle", "drop_first", "drop_last"]
    stats = {k: {"tried": 0, "caught": 0, "elsewhere": 0} for k in kinds}
    skipped = {"not_ok": 0, "short": 0}
    for r in rows:
        q = norm(r["quote"])
        hay = "".join(texts[r["a"] - 1:r["b"]])
        if q not in hay:
            skipped["not_ok"] += 1
            continue
        if len(q) < min_len:
            skipped["short"] += 1
            continue
        for k, m in mutants(q).items():
            s = stats[k]
            s["tried"] += 1
            if m not in hay:
                s["caught"] += 1
                if any(m in t for t in texts):
                    s["elsewhere"] += 1
    return stats, skipped


def summarize(results):
    out = {"rows": len(results)}
    for v in ("OK", "ELSEWHERE", "MISSING"):
        out[v] = sum(1 for r in results if r["verdict"] == v)
    for fl in ("SHORT", "MULTI", "DUP", "LINE"):
        out[fl] = sum(1 for r in results if fl in r["flags"])
    out["distinct"] = out["rows"] - out["DUP"]
    lens = sorted(r["len"] for r in results)
    out["median_len"] = (lens[(len(lens) - 1) // 2] + lens[len(lens) // 2]) / 2 if lens else 0
    return out


def write_evidence(path, results):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["id", "page_from", "page_to", "length", "verdict", "flags", "found_on_pages"])
        for r in results:
            w.writerow([r["id"], r["a"], r["b"], r["len"], r["verdict"],
                        ",".join(r["flags"]), ",".join(r["found"])])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("source")
    ap.add_argument("quotes")
    ap.add_argument("--header-lines", type=int, default=1,
                    help="lines dropped from the top of every page (default 1)")
    ap.add_argument("--drop-line-regex", default=None,
                    help="drop lines matching this regex (with --note-footer, either is dropped)")
    ap.add_argument("--note-footer", action="store_true",
                    help=f"drop lines starting with a note.com URL ({NOTE_FOOTER}), "
                         "including a body line that is only a link")
    ap.add_argument("--short", type=int, default=10)
    ap.add_argument("--mutate", action="store_true")
    ap.add_argument("--evidence", default=None)
    ap.add_argument("--quiet", action="store_true", help="print only the summary")
    args = ap.parse_args(argv)
    regex = [r for r in (args.drop_line_regex, NOTE_FOOTER if args.note_footer else None) if r]
    try:
        pages = read_pages(args.source, args.header_lines, regex)
        rows = load_quotes(args.quotes)
        texts = page_texts(pages)
        line_sets = [set(norm(ln) for ln in p if norm(ln)) for p in pages]
        results = check(texts, line_sets, rows, args.short)
    except (OSError, ValueError) as e:
        print(f"quotecheck: {e}", file=sys.stderr)
        return 2
    if not args.quiet:
        for r in results:
            if r["verdict"] != "OK":
                where = ",".join(r["found"]) or "-"
                print(f"{r['verdict']}\tid {r['id']}\tgiven p.{r['a']}-{r['b']}\tfound on {where}")
    s = summarize(results)
    print(f"source pages: {len(texts)}")
    print(f"rows: {s['rows']} (distinct after normalization: {s['distinct']})")
    print(f"OK: {s['OK']}  ELSEWHERE: {s['ELSEWHERE']}  MISSING: {s['MISSING']}")
    print(f"flags: SHORT(<={args.short}) {s['SHORT']}  MULTI {s['MULTI']}  DUP {s['DUP']}  LINE {s['LINE']}")
    print(f"median length: {s['median_len']:g}")
    if args.mutate:
        stats, skipped = mutate(texts, rows)
        print(f"self-test (OK quotations of 4+ characters; left out: {skipped['not_ok']} not OK,"
              f" {skipped['short']} under 4 characters):")
        for k, v in stats.items():
            print(f"  {k}: caught {v['caught']} of {v['tried']}"
                  f" (of the caught, {v['elsewhere']} occur on other pages)")
    if args.evidence:
        try:
            write_evidence(args.evidence, results)
        except OSError as e:
            print(f"quotecheck: cannot write evidence: {e}", file=sys.stderr)
            return 2
    return 0 if s["ELSEWHERE"] == 0 and s["MISSING"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
