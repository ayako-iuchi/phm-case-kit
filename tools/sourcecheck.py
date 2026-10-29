#!/usr/bin/env python3
"""sourcecheck — check a register that traces each real-world fact to its source.

Usage:
    sourcecheck.py REGISTER.tsv [--as-of YYYY-MM-DD] [--quiet]

A document such as a case study states real-world facts: a statistic, a
law, a standard. The register has one row per fact and records where the
fact was traced: to a primary source (a white paper, a government page, a
statistic, a standard), only to a secondary source (a column that does not
name its own source), or nowhere. This tool checks the register, not the
facts: it cannot open a source. It reports rows that do not say enough to be
checked by someone else, and counts the rows by class.

Columns (tab-separated, header row required, other columns ignored):
    id            unique id
    document      the document that states the fact
    page          page in that document
    statement     the fact as the document states it, short
    cited_ref     the document's own reference for it ("-" if none)
    source_kind   primary | secondary | none
    source_title  title of the source the fact was traced to
    issuer        who issued it
    edition       edition or date of the source
    url           URL, if the source is on the web
    location      page, section or table in the source
    underlying    the statistic or survey the source itself rests on ("-" if none)
    accessed      date the source was opened (YYYY-MM-DD)
    class         A | B | C | D | E
    note          what differs, or why it could not be checked

Classes:
    A  the primary source says it, as the document wrote it
    B  the primary source says it, but the document dropped or changed a
       qualifier, premise, year, scope or unit
    C  found only in a secondary source; no primary source located
    D  the primary source says something different
    E  could not be checked (for example a quotation with no source)

Checks:
    R1  a required field is empty: id, document, page, statement, source_kind,
        class (and note for B, C, D, E)
    R2  class or source_kind is not one of the allowed values
    R3  class A, B or D without a primary source (source_kind primary, with
        source_title and location)
    R4  class C whose source_kind is not secondary, or with no source_title
    R5  a URL without an accessed date, or an accessed date (with or
        without a URL) that is not YYYY-MM-DD or is later than --as-of
        (default: today)
    R6  a duplicate id
    R7  class E with a source: source_kind other than none, or a
        source_title, url or location filled in

Exit status: 0 if no check fires, 1 if any does, 2 on bad input.
"""
import argparse
import csv
import datetime as dt
import re
import sys

REQUIRED = ["id", "document", "page", "statement", "cited_ref", "source_kind",
            "source_title", "issuer", "edition", "url", "location", "underlying",
            "accessed", "class", "note"]
CLASSES = "ABCDE"
KINDS = ("primary", "secondary", "none")


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        try:
            header = next(reader, None)
        except csv.Error as e:
            raise ValueError(f"{path}: {e}")
        if header is None:
            raise ValueError(f"{path}: empty file")
        dups = sorted({c for c in header if header.count(c) > 1})
        if dups:
            raise ValueError(f"{path}: header names {', '.join(dups)} more than once")
        missing = [c for c in REQUIRED if c not in header]
        if missing:
            raise ValueError(f"{path}: header lacks {', '.join(missing)}")
        rows = []
        for n, fields in enumerate(_rows(reader, path), start=2):
            if not any(x.strip() for x in fields):
                continue
            if len(fields) != len(header):
                raise ValueError(f"{path}:{n}: {len(fields)} fields, header has {len(header)}")
            r = {k: v.strip() for k, v in zip(header, fields)}
            r["_line"] = n
            rows.append(r)
        if not rows:
            raise ValueError(f"{path}: no rows")
        return rows


DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _rows(reader, path):
    try:
        yield from reader
    except csv.Error as e:  # e.g. a field larger than the csv module allows
        raise ValueError(f"{path}: {e}")


def parse_date(s):
    """A date written as YYYY-MM-DD, or None. Other ISO forms are refused."""
    if not DATE.fullmatch(s):
        return None
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def check(rows, as_of):
    issues = []
    seen = {}

    def flag(r, code, msg):
        issues.append((r["_line"], r.get("id", ""), code, msg))

    for r in rows:
        cls, kind = r["class"], r["source_kind"]
        for k in ("id", "document", "page", "statement", "source_kind", "class"):
            if not r[k]:
                flag(r, "R1", f"{k} is empty")
        if cls in ("B", "C", "D", "E") and not r["note"]:
            flag(r, "R1", f"class {cls} needs a note")
        if cls and (len(cls) != 1 or cls not in CLASSES):
            flag(r, "R2", f"class {cls!r} is not one of A-E")
        if kind and kind not in KINDS:
            flag(r, "R2", f"source_kind {kind!r} is not one of {', '.join(KINDS)}")
        if cls in ("A", "B", "D"):
            if kind != "primary" or not r["source_title"] or not r["location"]:
                flag(r, "R3", f"class {cls} needs a primary source with a title and a location")
        if cls == "C" and (kind != "secondary" or not r["source_title"]):
            flag(r, "R4", "class C needs the secondary source it was found in")
        if cls == "E" and (kind not in ("none", "") or r["source_title"] or r["url"] or r["location"]):
            flag(r, "R7", "class E should have no source (source_kind none, no title, url or location)")
        if r["url"] and not r["accessed"]:
            flag(r, "R5", "url without an accessed date")
        if r["accessed"]:
            d = parse_date(r["accessed"])
            if d is None:
                flag(r, "R5", f"accessed {r['accessed']!r} is not YYYY-MM-DD")
            elif d > as_of:
                flag(r, "R5", f"accessed {r['accessed']} is after {as_of}")
        if r["id"]:
            if r["id"] in seen:
                flag(r, "R6", f"id also on line {seen[r['id']]}")
            else:
                seen[r["id"]] = r["_line"]
    return issues


def summary(rows):
    by_class = {c: 0 for c in CLASSES}
    by_kind = {k: 0 for k in KINDS}
    for r in rows:
        if r["class"] in by_class:
            by_class[r["class"]] += 1
        if r["source_kind"] in by_kind:
            by_kind[r["source_kind"]] += 1
    return by_class, by_kind


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("register")
    ap.add_argument("--as-of", default=None, help="date for the accessed check (default: today)")
    ap.add_argument("--quiet", action="store_true", help="print only the summary")
    args = ap.parse_args(argv)
    try:
        as_of = parse_date(args.as_of) if args.as_of else dt.date.today()
        if as_of is None:
            raise ValueError(f"--as-of {args.as_of!r} is not YYYY-MM-DD")
        rows = load(args.register)
    except (OSError, ValueError) as e:
        print(f"sourcecheck: {e}", file=sys.stderr)
        return 2
    issues = check(rows, as_of)
    if not args.quiet:
        for line, rid, code, msg in issues:
            print(f"{code}\tline {line}\tid {rid}\t{msg}")
    by_class, by_kind = summary(rows)
    print(f"rows: {len(rows)}")
    print("class: " + "  ".join(f"{c} {n}" for c, n in by_class.items()))
    print("source: " + "  ".join(f"{k} {n}" for k, n in by_kind.items()))
    print(f"issues: {len(issues)}")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
