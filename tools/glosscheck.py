#!/usr/bin/env python3
"""glosscheck — check English versions against a glossary of fixed renderings.

Usage:
    glosscheck.py GLOSSARY.tsv EN.md [EN.md ...] [--pair JA.md=EN.md ...]
                  [--quiet]

A series translated from Japanese drifts: the same Japanese term gets one
English rendering in one post and another in the next, and a rendering the
series decided never to use slips back in. The glossary has one row per
Japanese term, with the rendering to use, renderings seen that differ from
it, and renderings never to use. This tool counts, in each English file, the
renderings to avoid and the variants, and, for a Japanese file paired with
its English version, the terms whose Japanese is there but whose rendering
is not. It checks wording, not meaning.

Glossary columns (tab-separated, header row required, other columns ignored):
    id        unique id
    ja        the Japanese term as it appears in the Japanese text
    en        the rendering to use; several accepted forms separated by " | "
    variants  renderings seen that differ from it, " | "-separated, or "-"
    avoid     renderings never to use, " | "-separated, or "-"
    note      why

Matching. English forms are matched case-insensitively, as whole words where
the form starts or ends with a letter or digit; a form ending in a letter
also matches its plural in -s or -es ("outline templates"). A space or a
hyphen in a form matches any run of spaces, line breaks or hyphens
("business plan template" matches "business-plan template"). A form that contains a
capital letter is matched case-sensitively after its first letter, so
"Predictive Maintenance" does not match "predictive maintenance"; a form
with no capital letter
matches in any case. Japanese terms are matched as plain substrings.

Findings (each makes the exit status 1):
    AVOID    a rendering never to use appears
    VARIANT  a variant appears
    MISSING  (--pair only) the Japanese term is in the Japanese file, but
             neither the rendering nor a variant is in the English file

Within a row, text inside a match of the rendering to use is not reported,
and where two forms overlap only the longer is; forms of different rows are
not compared. A line break counts as a space, but a blank line, a list item
or a heading does not. The first letter of a form with a capital letter may
be in either case (the start of a sentence). Words are matched, not
meanings: a lowercase form also matches the same words capitalised at the
start of a sentence or in a name, and the tool cannot tell when one English
word is used for two Japanese terms. A post may mention a rendering to avoid
in order to say it is not used; the tool still reports it, and the person
reading the report decides.

Register problems (exit status 1): G1 a required field is empty, G2 a
duplicate id, G3 the same form listed twice in one row. Exit status 2 on bad
input.
"""
import argparse
import csv
import re
import sys

REQUIRED = ["id", "ja", "en", "variants", "avoid", "note"]


def forms(cell):
    if cell.strip() in ("", "-"):
        return []
    return [f.strip() for f in cell.split(" | ") if f.strip()]


SEP = r"(?:[ \t\u00a0\-\u2010\u2011]|\r?\n(?![ \t]*(?:\r?\n|[-*+] |#|\d+\. )))+"


def pattern(form):
    flags = 0 if any(c.isupper() for c in form) else re.I
    left = r"(?<![A-Za-z0-9])" if form[0].isalnum() else ""
    right = r"(?:s|es)?(?![A-Za-z0-9])" if form[-1].isalpha() else (r"(?![A-Za-z0-9])" if form[-1].isalnum() else "")
    words = [w for w in re.split(r"[\s\-]+", form.strip()) if w]
    body = SEP.join(re.escape(w) for w in words)
    if flags == 0 and body[:1].isalpha():
        body = f"(?i:{body[0]})" + body[1:]
    return re.compile(left + body + right, flags)


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        try:
            header = next(reader, None)
            if header is None:
                raise ValueError(f"{path}: empty file")
            missing = [c for c in REQUIRED if c not in header]
            if missing:
                raise ValueError(f"{path}: header lacks {', '.join(missing)}")
            if len(set(header)) != len(header):
                raise ValueError(f"{path}: a header name appears more than once")
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


def check_glossary(rows):
    issues, seen = [], {}
    for r in rows:
        for k in ("id", "ja", "en", "note"):
            if not r[k] or (k == "en" and not forms(r[k])):
                issues.append((r["_line"], r["id"], "G1", f"{k} is empty"))
        if r["id"]:
            if r["id"] in seen:
                issues.append((r["_line"], r["id"], "G2", f"id also on line {seen[r['id']]}"))
            seen.setdefault(r["id"], r["_line"])
        all_forms = forms(r["en"]) + forms(r["variants"]) + forms(r["avoid"])
        dup = sorted({f for f in all_forms if all_forms.count(f) > 1})
        if dup:
            issues.append((r["_line"], r["id"], "G3", f"listed twice: {', '.join(dup)}"))
    return issues


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def check_text(rows, en_text, ja_text=None):
    """Return a list of (line, id, code, message) for one English text."""
    out = []
    for r in rows:
        if not forms(r["en"]):
            continue
        # spans of the accepted forms are not reported; among the other forms,
        # longer ones are matched first, and a span is reported only once
        inside = [m.span() for f in forms(r["en"]) for m in pattern(f).finditer(en_text)]
        taken = []
        cands = [(len(f), f, kind) for kind, cell in (("AVOID", r["avoid"]), ("VARIANT", r["variants"]))
                 for f in forms(cell)]
        for _, form, kind in sorted(cands, key=lambda c: -c[0]):
            for m in pattern(form).finditer(en_text):
                a, b = m.span()
                if any(x <= a and b <= y for x, y in inside) or any(a < y and x < b for x, y in taken):
                    continue
                taken.append((a, b))
                out.append((line_of(en_text, a), r["id"], kind,
                            f"«{m.group(0)}» for {r['ja']}; use «{forms(r['en'])[0]}»"))
        if ja_text is not None and r["ja"] in ja_text:
            ok = forms(r["en"]) + forms(r["variants"])
            if not any(pattern(f).search(en_text) for f in ok):
                out.append((0, r["id"], "MISSING", f"{r['ja']} is in the Japanese; «{forms(r['en'])[0]}» is not in the English"))
    return sorted(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("glossary")
    ap.add_argument("en", nargs="*", help="English files")
    ap.add_argument("--pair", action="append", default=[], metavar="JA=EN")
    ap.add_argument("--quiet", action="store_true", help="print only the summary")
    args = ap.parse_args(argv)
    try:
        rows = load(args.glossary)
        jobs = [(p, None) for p in args.en]
        for spec in args.pair:
            if "=" not in spec:
                raise ValueError(f"--pair {spec!r} is not JA=EN")
            ja, en = spec.split("=", 1)
            jobs.append((en, ja))
        if not jobs:
            raise ValueError("no English file given")
        texts = []
        for en, ja in jobs:
            with open(en, encoding="utf-8-sig") as f:
                en_text = f.read()
            ja_text = None
            if ja:
                with open(ja, encoding="utf-8-sig") as f:
                    ja_text = f.read()
            texts.append((en, en_text, ja_text))
    except (OSError, ValueError, UnicodeDecodeError) as e:
        print(f"glosscheck: {e}", file=sys.stderr)
        return 2
    issues = check_glossary(rows)
    total = {"AVOID": 0, "VARIANT": 0, "MISSING": 0}
    if not args.quiet:
        for line, rid, code, msg in issues:
            print(f"{code}\tline {line}\tid {rid}\t{msg}")
    for name, en_text, ja_text in texts:
        found = check_text(rows, en_text, ja_text)
        for _, _, code, _ in found:
            total[code] += 1
        if not args.quiet:
            for line, rid, code, msg in found:
                print(f"{code}\t{name}:{line}\tid {rid}\t{msg}")
    print(f"glossary: {len(rows)} terms  files: {len(texts)}")
    print("findings: " + "  ".join(f"{k} {v}" for k, v in total.items()))
    print(f"issues: {len(issues)}")
    return 1 if issues or any(total.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
