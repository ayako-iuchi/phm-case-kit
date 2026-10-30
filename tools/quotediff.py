#!/usr/bin/env python3
"""quotediff — find how a quotation differs from its source.

Usage:
    quotediff.py REGISTER.tsv --text SOURCE=PATH [--text ...]
                 [--header-lines N] [--note-footer] [--min-ratio R] [--quiet]

quotecheck says whether a quotation is on its page. This tool goes one step
further for quotations that are not: it finds the passage in the source that
the quotation most resembles and lists how they differ (words left out, words
added, words replaced), so that a reworded line presented as a quotation can
be told apart from a faithful one, an omission marked with an ellipsis, and a
paraphrase the document says is a paraphrase.

Columns (tab-separated, header row required, other columns ignored):
    id       unique id
    document the document that presents the quotation
    page     page in that document
    source   the source it is attributed to: a SOURCE given with --text
    quote    the quotation as the document gives it, without its quote marks
    marked   how the document marks it: none | ellipsis | paraphrase
             (ellipsis: omissions are shown with … or ...; paraphrase: the
             document says it is a summary or paraphrase)
    note     anything else

Matching. Both texts are compared after removing all whitespace and applying
Unicode NFKC (so full-width and half-width letters and digits match; 「」 and
"" still differ). The source is one pdftotext extract with form feeds between
pages; --header-lines and --note-footer drop page headers and note.com
footers as in quotecheck, and the page reported is the page where the
matching passage starts.

Classes:
    EXACT       the quotation is in the source as it stands
    ELLIPSIS    marked ellipsis, and every part between the ellipses is in
                the source, in order
    PARAPHRASE  marked paraphrase and not EXACT (reported, not a finding)
    ALTERED     not in the source, but a passage resembles it (similarity at
                least --min-ratio, default 0.6); the changes are listed
    NOT-FOUND   no passage resembles it that closely

Similarity is 2M / (a + b), where M is the number of characters the
quotation and the passage share in order and a and b are their lengths
(difflib). The passage is located by counting shared 4-character sequences;
of the spans between matching characters there, the one most like the
quotation is kept.

Findings (exit status 1): ALTERED and NOT-FOUND, and an ELLIPSIS row whose
parts are not all in the source in order (reported as ALTERED or NOT-FOUND).
Register problems (exit status 1): Q1 a required field is empty or a value is
not allowed, Q2 a source with no --text, Q3 a duplicate id. Exit status 2 on
bad input.

The register is the author's: it should hold quotations of documents whose
text you may copy. For a source you may not copy, keep the rows elsewhere.
"""
import argparse
import csv
import difflib
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pages import read_pages  # noqa: E402

REQUIRED = ["id", "document", "page", "source", "quote", "marked", "note"]
MARKS = ("none", "ellipsis", "paraphrase")
ELLIPSIS = re.compile(r"(?:…+|\.{3,}|・{3,}|／)")
NGRAM = 4
MAX_BLOCKS = 40
MAX_QUOTE = 2000


def norm(s):
    return "".join(ch for ch in unicodedata.normalize("NFKC", s) if not ch.isspace())


class Source:
    """A source text as one normalized string, with the page of each character."""

    def __init__(self, pages):
        parts, starts, pos = [], [], 0
        for lines in pages:
            t = norm("".join(lines))
            starts.append(pos)
            parts.append(t)
            pos += len(t)
        self.text = "".join(parts)
        self.starts = starts
        self.index = {}
        for i in range(len(self.text) - NGRAM + 1):
            self.index.setdefault(self.text[i:i + NGRAM], []).append(i)

    def page_of(self, pos):
        lo, hi = 0, len(self.starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    def best(self, q):
        """(similarity, start, end, opcodes) of the passage most like q, or None."""
        votes = {}
        for j in range(len(q) - NGRAM + 1):
            for i in self.index.get(q[j:j + NGRAM], ()):
                votes[i - j] = votes.get(i - j, 0) + 1
        if not votes:
            return None
        best = None
        for off, _ in sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))[:5]:
            pad = len(q) // 2 + NGRAM
            lo, hi = max(0, off - pad), min(len(self.text), off + len(q) + pad)
            window = self.text[lo:hi]
            sm = difflib.SequenceMatcher(None, window, q, autojunk=False)
            blocks = [b for b in sm.get_matching_blocks() if b.size]
            if not blocks:
                continue
            # Trim to the span of matching blocks that resembles q most, so a
            # stray one-character match at either end does not widen it.
            if len(blocks) > MAX_BLOCKS:
                blocks = sorted(sorted(blocks, key=lambda b: -b.size)[:MAX_BLOCKS], key=lambda b: b.a)
            for i in range(len(blocks)):
                for j in range(i, len(blocks)):
                    a0, a1 = blocks[i].a, blocks[j].a + blocks[j].size
                    passage = window[a0:a1]
                    sm2 = difflib.SequenceMatcher(None, passage, q, autojunk=False)
                    ratio = sm2.ratio()
                    if best is None or ratio > best[0]:
                        best = (ratio, lo + a0, lo + a1, sm2.get_opcodes(), passage)
        return best


def changes(opcodes, passage, q, width=24):
    out = []

    def cut(s):
        return s if len(s) <= width else s[:width] + "…"

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "delete":
            out.append(f"omitted «{cut(passage[i1:i2])}»")
        elif tag == "insert":
            out.append(f"added «{cut(q[j1:j2])}»")
        elif tag == "replace":
            out.append(f"replaced «{cut(passage[i1:i2])}» with «{cut(q[j1:j2])}»")
    return out


def classify(row, src, min_ratio):
    """Return (class, detail)."""
    q = norm(row["quote"])
    if row["marked"] == "ellipsis":
        parts = [norm(p) for p in ELLIPSIS.split(row["quote"]) if norm(p)]
        pos, ok, where = 0, True, None
        for p in parts:
            i = src.text.find(p, pos)
            if i < 0:
                ok = False
                break
            where = i if where is None else where
            pos = i + len(p)
        if ok and parts:
            return "ELLIPSIS", f"source p.{src.page_of(where)}"
        q = "".join(parts)
    i = src.text.find(q) if q else -1
    if i >= 0:
        return "EXACT", f"source p.{src.page_of(i)}"
    found = src.best(q) if q else None
    if found is None or found[0] < min_ratio:
        ratio = f"{found[0]:.2f}" if found else "0.00"
        return ("PARAPHRASE" if row["marked"] == "paraphrase" else "NOT-FOUND",
                f"best similarity {ratio}")
    ratio, start, _, ops, passage = found
    detail = f"source p.{src.page_of(start)}, similarity {ratio:.2f}: " + "; ".join(changes(ops, passage, q))
    return ("PARAPHRASE" if row["marked"] == "paraphrase" else "ALTERED"), detail


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
            rows = []
            for n, fields in enumerate(reader, start=2):
                if not any(x.strip() for x in fields):
                    continue
                if len(fields) != len(header):
                    raise ValueError(f"{path}:{n}: {len(fields)} fields, header has {len(header)}")
                r = {k: v.strip() for k, v in zip(header, fields)}
                r["_line"] = n
                rows.append(r)
        except csv.Error as e:
            raise ValueError(f"{path}: {e}")
    if not rows:
        raise ValueError(f"{path}: no rows")
    return rows


def check(rows, sources, min_ratio=0.6):
    """Return (issues, results). results: list of (line, id, class, detail)."""
    issues, results, seen = [], [], {}
    for r in rows:
        bad = False
        for k in ("id", "document", "page", "source", "quote", "marked"):
            if not r[k]:
                issues.append((r["_line"], r["id"], "Q1", f"{k} is empty"))
                bad = True
        if r["marked"] and r["marked"] not in MARKS:
            issues.append((r["_line"], r["id"], "Q1", f"marked {r['marked']!r} is not one of {', '.join(MARKS)}"))
            bad = True
        if len(r["quote"]) > MAX_QUOTE:
            issues.append((r["_line"], r["id"], "Q1", f"quote is longer than {MAX_QUOTE} characters"))
            bad = True
        if r["source"] and r["source"] not in sources:
            issues.append((r["_line"], r["id"], "Q2", f"source {r['source']!r} has no --text"))
            bad = True
        if r["id"]:
            if r["id"] in seen:
                issues.append((r["_line"], r["id"], "Q3", f"id also on line {seen[r['id']]}"))
            else:
                seen[r["id"]] = r["_line"]
        if not bad:
            cls, detail = classify(r, sources[r["source"]], min_ratio)
            results.append((r["_line"], r["id"], cls, detail))
    return issues, results


CLASSES = ("EXACT", "ELLIPSIS", "PARAPHRASE", "ALTERED", "NOT-FOUND")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("register")
    ap.add_argument("--text", action="append", default=[], metavar="SOURCE=PATH",
                    help="a source's pdftotext extract (repeatable)")
    ap.add_argument("--header-lines", type=int, default=0, help="lines to drop from the top of every page (default 0)")
    ap.add_argument("--note-footer", action="store_true", help="drop lines that start with a note.com URL")
    ap.add_argument("--min-ratio", type=float, default=0.6, help="similarity for ALTERED (default 0.6)")
    ap.add_argument("--quiet", action="store_true", help="print only the summary")
    args = ap.parse_args(argv)
    try:
        if args.header_lines < 0:
            raise ValueError("--header-lines must be 0 or more")
        if not 0 < args.min_ratio <= 1:
            raise ValueError("--min-ratio must be more than 0 and at most 1")
        drop = [r"^https://note\.com/"] if args.note_footer else None
        sources = {}
        for spec in args.text:
            if "=" not in spec:
                raise ValueError(f"--text {spec!r} is not SOURCE=PATH")
            name, path = spec.split("=", 1)
            if name in sources:
                raise ValueError(f"--text names {name} twice")
            sources[name] = Source(read_pages(path, header_lines=args.header_lines, drop_line_regex=drop))
        rows = load(args.register)
    except (OSError, ValueError, UnicodeDecodeError) as e:
        print(f"quotediff: {e}", file=sys.stderr)
        return 2
    issues, results = check(rows, sources, args.min_ratio)
    if not args.quiet:
        for line, rid, code, msg in sorted(issues + results, key=lambda x: x[0]):
            print(f"{code}\tline {line}\tid {rid}\t{msg}")
    counts = {c: sum(1 for _, _, k, _ in results if k == c) for c in CLASSES}
    print(f"rows: {len(rows)}")
    print("class: " + "  ".join(f"{c} {n}" for c, n in counts.items()))
    print(f"issues: {len(issues)}")
    return 1 if issues or counts["ALTERED"] or counts["NOT-FOUND"] else 0


if __name__ == "__main__":
    sys.exit(main())
