#!/usr/bin/env python3
"""datecheck — check a register of dated facts: true as of when?

Usage:
    datecheck.py REGISTER.tsv [--as-of YYYY-MM-DD] [--quiet]

Some facts are true only as of a date: a tax measure abolished on a given
day, the latest edition of a white paper, a framework's current version, a
body that has since been disbanded. A document states such a fact on its own
date; someone checks it on a later date. The register has one row per fact
and keeps the three dates apart: the document's date, the date of the event
that decides the fact, and the date the source was opened. It records
whether the fact held on the document's date and whether it holds now, and
a date by which the row should be checked again. This tool checks the
register, not the facts: it cannot open a source.

Columns (tab-separated, header row required, other columns ignored):
    id            unique id
    document      the document that states the fact
    page          page in that document
    statement     the fact as the document states it, short
    doc_date      the document's date: YYYY-MM-DD, or <=YYYY-MM-DD when
                  only an upper bound is known
    event         the event that decides whether the fact holds
    event_date    its date: YYYY, YYYY-MM or YYYY-MM-DD ("-" if none)
    status_then   true | false | unknown: did the fact hold on doc_date?
    status_now    true | false | unknown: does it hold on the date checked?
    source_title  the source that settles it
    url           its URL, if on the web
    accessed      date the source was opened (YYYY-MM-DD)
    recheck_by    date by which the row should be checked again (YYYY-MM-DD)
    class         CURRENT | STALE | WRONG-THEN | UNDATED | CANNOT
    note          what changed, or what date is missing

Classes:
    CURRENT     held on the document's date and holds now
    STALE       held on the document's date, no longer holds
    WRONG-THEN  did not hold even on the document's date
    UNDATED     depends on a date the document does not give
    CANNOT      could not be checked

Checks:
    T1  a required field is empty: id, document, page, statement, doc_date,
        event, status_then, status_now, class (and note for every class but
        CURRENT)
    T2  a value is not allowed (class, status, a date's form)
    T3  class and statuses disagree: CURRENT needs true/true, STALE
        true/false, WRONG-THEN false then, CANNOT unknown/unknown
    T4  hindsight: WRONG-THEN whose event comes after the document's date
        (a later change does not make a statement wrong when written), or
        STALE whose event comes before it (it had already changed)
    T5  a URL without an accessed date, or an accessed date after --as-of
    T6  a duplicate id
    T7  recheck due: recheck_by is on or before --as-of (default: today)

An event dated only by year or month is compared by its whole period: it
comes after a document only if its first day does, and before it only if
its last day does; otherwise T4 does not fire. A doc_date given as <=DATE
counts as that date for "after" and is not used for "before".

Exit status: 0 if no check fires, 1 if any does, 2 on bad input.
"""
import argparse
import calendar
import csv
import datetime as dt
import re
import sys

REQUIRED = ["id", "document", "page", "statement", "doc_date", "event", "event_date",
            "status_then", "status_now", "source_title", "url", "accessed", "recheck_by",
            "class", "note"]
CLASSES = ("CURRENT", "STALE", "WRONG-THEN", "UNDATED", "CANNOT")
STATUSES = ("true", "false", "unknown")
DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_day(s):
    if not DAY.fullmatch(s):
        return None
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def parse_period(s):
    """'2024' / '2024-04' / '2024-04-01' -> (first day, last day), or None."""
    try:
        if re.fullmatch(r"\d{4}", s):
            y = int(s)
            return dt.date(y, 1, 1), dt.date(y, 12, 31)
        if re.fullmatch(r"\d{4}-\d{2}", s):
            y, m = int(s[:4]), int(s[5:])
            return dt.date(y, m, 1), dt.date(y, m, calendar.monthrange(y, m)[1])
    except ValueError:
        return None
    d = parse_day(s)
    return (d, d) if d else None


def parse_doc_date(s):
    """'2026-05-21' -> (date, exact=True); '<=2026-08-25' -> (date, False); None if bad."""
    if s.startswith("<="):
        d = parse_day(s[2:])
        return (d, False) if d else None
    d = parse_day(s)
    return (d, True) if d else None


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


def check(rows, as_of):
    issues, seen = [], {}

    def flag(r, code, msg):
        issues.append((r["_line"], r.get("id", ""), code, msg))

    for r in rows:
        cls, then, now = r["class"], r["status_then"], r["status_now"]
        for k in ("id", "document", "page", "statement", "doc_date", "event",
                  "status_then", "status_now", "class"):
            if not r[k]:
                flag(r, "T1", f"{k} is empty")
        if cls and cls != "CURRENT" and not r["note"]:
            flag(r, "T1", f"class {cls} needs a note")
        if cls and cls not in CLASSES:
            flag(r, "T2", f"class {cls!r} is not one of {', '.join(CLASSES)}")
        for k in ("status_then", "status_now"):
            if r[k] and r[k] not in STATUSES:
                flag(r, "T2", f"{k} {r[k]!r} is not true, false or unknown")
        doc = parse_doc_date(r["doc_date"]) if r["doc_date"] else None
        if r["doc_date"] and doc is None:
            flag(r, "T2", f"doc_date {r['doc_date']!r} is not YYYY-MM-DD or <=YYYY-MM-DD")
        ev = None
        if r["event_date"] and r["event_date"] != "-":
            ev = parse_period(r["event_date"])
            if ev is None:
                flag(r, "T2", f"event_date {r['event_date']!r} is not YYYY, YYYY-MM or YYYY-MM-DD")
        for k in ("accessed", "recheck_by"):
            if r[k] and parse_day(r[k]) is None:
                flag(r, "T2", f"{k} {r[k]!r} is not YYYY-MM-DD")
        expect = {"CURRENT": ("true", "true"), "STALE": ("true", "false"),
                  "CANNOT": ("unknown", "unknown")}.get(cls)
        if expect and (then, now) != expect:
            flag(r, "T3", f"class {cls} needs status_then={expect[0]}, status_now={expect[1]}")
        if cls == "WRONG-THEN" and then != "false":
            flag(r, "T3", "class WRONG-THEN needs status_then=false")
        if doc and ev:
            d, exact = doc
            if cls == "WRONG-THEN" and ev[0] > d:
                flag(r, "T4", f"WRONG-THEN, but the event ({r['event_date']}) comes after the document ({r['doc_date']})")
            if cls == "STALE" and exact and ev[1] < d:
                flag(r, "T4", f"STALE, but the event ({r['event_date']}) comes before the document ({r['doc_date']})")
        acc = parse_day(r["accessed"]) if r["accessed"] else None
        if r["url"] and not r["accessed"]:
            flag(r, "T5", "url without an accessed date")
        if acc and acc > as_of:
            flag(r, "T5", f"accessed {r['accessed']} is after {as_of}")
        due = parse_day(r["recheck_by"]) if r["recheck_by"] else None
        if due and due <= as_of:
            flag(r, "T7", f"recheck due: recheck_by {r['recheck_by']} is on or before {as_of}")
        if r["id"]:
            if r["id"] in seen:
                flag(r, "T6", f"id also on line {seen[r['id']]}")
            else:
                seen[r["id"]] = r["_line"]
    return issues


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("register")
    ap.add_argument("--as-of", default=None, help="date for the accessed and recheck checks (default: today)")
    ap.add_argument("--quiet", action="store_true", help="print only the summary")
    args = ap.parse_args(argv)
    try:
        as_of = parse_day(args.as_of) if args.as_of else dt.date.today()
        if as_of is None:
            raise ValueError(f"--as-of {args.as_of!r} is not YYYY-MM-DD")
        rows = load(args.register)
    except (OSError, ValueError, UnicodeDecodeError) as e:
        print(f"datecheck: {e}", file=sys.stderr)
        return 2
    issues = check(rows, as_of)
    if not args.quiet:
        for line, rid, code, msg in issues:
            print(f"{code}\tline {line}\tid {rid}\t{msg}")
    counts = {c: sum(r["class"] == c for r in rows) for c in CLASSES}
    dues = [parse_day(r["recheck_by"]) for r in rows if parse_day(r["recheck_by"] or "")]
    print(f"rows: {len(rows)}")
    print("class: " + "  ".join(f"{c} {n}" for c, n in counts.items()))
    print(f"next recheck: {min(dues) if dues else '-'}")
    print(f"issues: {len(issues)}")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
