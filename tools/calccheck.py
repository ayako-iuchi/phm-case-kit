#!/usr/bin/env python3
"""calccheck — recalculate a register of numbers taken from a document.

Usage:
    calccheck.py REGISTER.tsv [--quiet]

A business plan shows numbers that should follow from other numbers: rows
that add up to a total, a rate times a base, a payback period from an
investment and a yearly benefit. This tool takes a register with one row per
number, recalculates every number that has a formula, and compares it with
the number as shown, at the precision it is shown. It checks the arithmetic
and the register, not what the numbers mean: it cannot tell a rate of hours
from a rate of money.

Columns (tab-separated, header row required, other columns ignored):
    id        unique id: a letter, then letters, digits or underscores
    document  the document the number comes from
    page      page in that document
    label     what the document calls it, short
    shown     the number as the document shows it, verbatim
    value     the shown number as a plain decimal in the register's unit
              (82% is 0.82), or "-" when the document gives none
    places    decimals to which the document shows it (0 or more), or "-"
    kind      input | derived | candidate | placeholder
    formula   for derived and candidate rows: + - * / and parentheses over
              decimal numbers and other rows' ids
    of        for candidate rows: the id of the shown number it tries to
              reproduce
    note      what the formula assumes, or where a value comes from

Kinds:
    input        a number the document gives and does not derive
    derived      a number the document shows together with how it is
                 derived (the formula is the document's own)
    candidate    one reading of how a shown number might have been
                 calculated, when the document does not say; several
                 candidates may point at the same number
    placeholder  a number the document leaves open ([X]) or does not give;
                 value is "-"

Checks (register problems; each makes the exit status 1):
    R1  a required field is empty or not allowed (id form, kind, value,
        places, a formula where none belongs or none where one is needed,
        "of" on a non-candidate or missing on a candidate)
    R2  a formula does not parse, is too long or nests too deeply, names an
        id not in the register, divides by zero, or gives a value past the
        size limit
    R3  a formula refers back to its own row, directly or through others
        (each row in the loop is reported)
    R4  a duplicate id
    R5  "of" names a row that is not input or derived, or has no value

Findings (about the document's arithmetic; each makes the exit status 1):
    MISMATCH    a derived row whose formula, rounded to the shown places,
                does not give the shown value
    NOREPRO     a shown number that has candidates, none of which gives it
    UNRESOLVED  a derived or candidate row whose formula needs a
                placeholder, so it cannot be calculated

A calculated value matches when it lies within half a unit of the last shown
place of the shown value (for 1.5 shown to 1 place: 1.45 to 1.55).
Arithmetic is exact (fractions); nothing is rounded before the comparison.
A formula that names a derived row uses that row's calculated value, not its
shown value; to use a shown value as it stands, record it as an input row.
A division by zero is R2 on the row whose formula divides. A row that only
depends on a row with a register problem is not reported again, and a shown
number whose candidates all fail on register problems gets no NOREPRO.
Rows are calculated in dependency order, so the order of rows does not
matter. Limits: a formula of at most 2000 characters, a value of at most 40
characters, places from 0 to 12, and calculated values of at most 4000 bits
(about 1200 digits; larger is R2).

Exit status: 0 if nothing fires, 1 if a check or finding fires, 2 on bad input.
"""
import argparse
import csv
import re
import sys
from fractions import Fraction

REQUIRED = ["id", "document", "page", "label", "shown", "value", "places", "kind",
            "formula", "of", "note"]
KINDS = ("input", "derived", "candidate", "placeholder")
ID = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
NUM = re.compile(r"[0-9]+(\.[0-9]+)?")
MAX_FORMULA = 2000
MAX_NUMBER = 40
MAX_PLACES = 12
MAX_BITS = 4000
TOKEN = re.compile(r"\s*(?:([0-9]+(?:\.[0-9]+)?)|([A-Za-z][A-Za-z0-9_]*)|(.))")


def parse_value(s):
    if not NUM.fullmatch(s or ""):
        return None
    return Fraction(s)


def tokens(formula):
    out = []
    for m in TOKEN.finditer(formula):
        num, name, op = m.groups()
        if num is not None:
            out.append(("num", Fraction(num)))
        elif name is not None:
            out.append(("id", name))
        elif op is not None and op.strip():
            if op not in "+-*/()":
                raise ValueError(f"character {op!r} is not allowed")
            out.append(("op", op))
    if not out:
        raise ValueError("empty formula")
    return out


def parse(formula):
    """Formula -> tree of ('num', F) / ('id', name) / (op, left, right) / ('neg', x)."""
    toks = tokens(formula)
    pos = [0]

    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else None

    def take():
        t = peek()
        pos[0] += 1
        return t

    def expr():
        node = term()
        while peek() in (("op", "+"), ("op", "-")):
            op = take()[1]
            node = (op, node, term())
        return node

    def term():
        node = unary()
        while peek() in (("op", "*"), ("op", "/")):
            op = take()[1]
            node = (op, node, unary())
        return node

    def unary():
        if peek() == ("op", "-"):
            take()
            return ("neg", unary())
        return atom()

    def atom():
        t = take()
        if t is None:
            raise ValueError("formula ends too early")
        if t[0] in ("num", "id"):
            return t
        if t == ("op", "("):
            node = expr()
            if take() != ("op", ")"):
                raise ValueError("missing )")
            return node
        raise ValueError(f"unexpected {t[1]!r}")

    tree = expr()
    if peek() is not None:
        raise ValueError(f"unexpected {peek()[1]!r}")
    return tree


def _children(node):
    if node[0] in ("num", "id"):
        return ()
    if node[0] == "neg":
        return (node[1],)
    return (node[1], node[2])


def names(tree):
    out, todo = set(), [tree]
    while todo:
        node = todo.pop()
        if node[0] == "id":
            out.add(node[1])
        todo.extend(_children(node))
    return out


class TooLarge(ValueError):
    pass


def evaluate(tree, env):
    """Post-order evaluation without recursion. Raises TooLarge past MAX_BITS."""
    done, todo = {}, [(tree, False)]
    while todo:
        node, ready = todo.pop()
        k = node[0]
        if k == "num":
            done[id(node)] = node[1]
            continue
        if k == "id":
            done[id(node)] = env(node[1])
            continue
        if not ready:
            todo.append((node, True))
            todo.extend((c, False) for c in _children(node))
            continue
        if k == "neg":
            v = -done.pop(id(node[1]))
        else:
            x, y = done.pop(id(node[1])), done.pop(id(node[2]))
            if k == "+":
                v = x + y
            elif k == "-":
                v = x - y
            elif k == "*":
                v = x * y
            else:
                if y == 0:
                    raise ZeroDivisionError("division by zero")
                v = x / y
        if max(v.numerator.bit_length(), v.denominator.bit_length()) > MAX_BITS:
            raise TooLarge("a calculated value is too large")
        done[id(node)] = v
    return done[id(tree)]


def matches(calc, value, places):
    return abs(calc - value) <= Fraction(1, 2) / Fraction(10) ** places


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


def fmt(x, places=4):
    """Fraction -> decimal string rounded half-even to `places`, without float."""
    q = Fraction(round(x * 10 ** places), 10 ** places)
    sign = "-" if q < 0 else ""
    q = abs(q)
    whole, frac = divmod(q.numerator * 10 ** places // q.denominator, 10 ** places)
    return f"{sign}{whole}.{frac:0{places}d}" if places else f"{sign}{whole}"


class _Skip(Exception):
    """A dependency has a register problem already reported; say nothing more."""


class _Open(Exception):
    def __init__(self, name):
        super().__init__(name)
        self.name = name


def check(rows):
    """Return (issues, findings, results). results: id -> calculated Fraction."""
    issues, findings = [], []
    by_id, trees, bad = {}, {}, set()

    def flag(r, code, msg):
        issues.append((r["_line"], r["id"], code, msg))
        if r["id"]:
            bad.add(r["id"])

    for r in rows:
        kind = r["kind"]
        for k in ("id", "document", "page", "label", "kind"):
            if not r[k]:
                flag(r, "R1", f"{k} is empty")
        if r["id"] and not ID.fullmatch(r["id"]):
            flag(r, "R1", f"id {r['id']!r} is not a letter followed by letters, digits or underscores")
        if kind and kind not in KINDS:
            flag(r, "R1", f"kind {kind!r} is not one of {', '.join(KINDS)}")
        r["_value"] = parse_value(r["value"]) if len(r["value"]) <= MAX_NUMBER else None
        r["_places"] = (int(r["places"]) if re.fullmatch(r"[0-9]{1,2}", r["places"] or "")
                        and int(r["places"]) <= MAX_PLACES else None)
        if kind in ("input", "derived"):
            if not r["shown"]:
                flag(r, "R1", "shown is empty")
            if r["_value"] is None:
                flag(r, "R1", f"value {r['value'][:40]!r} is not a plain decimal of at most {MAX_NUMBER} characters")
            if r["_places"] is None:
                flag(r, "R1", f"places {r['places'][:40]!r} is not a whole number from 0 to {MAX_PLACES}")
        if kind == "placeholder" and r["value"] != "-":
            flag(r, "R1", "a placeholder's value is \"-\"")
        if kind in ("derived", "candidate") and not r["formula"]:
            flag(r, "R1", f"a {kind} row needs a formula")
        if kind in ("input", "placeholder") and r["formula"]:
            flag(r, "R1", f"an input row takes no formula" if kind == "input" else "a placeholder row takes no formula")
        if kind == "candidate" and not r["of"]:
            flag(r, "R1", "a candidate row needs \"of\"")
        if kind != "candidate" and r["of"]:
            flag(r, "R1", "only a candidate row has \"of\"")
        if r["id"] and ID.fullmatch(r["id"]):
            if r["id"] in by_id:
                flag(r, "R4", f"id also on line {by_id[r['id']]['_line']}")
                continue
            by_id[r["id"]] = r
            if r["formula"]:
                if len(r["formula"]) > MAX_FORMULA:
                    flag(r, "R2", f"formula is longer than {MAX_FORMULA} characters")
                    continue
                try:
                    trees[r["id"]] = parse(r["formula"])
                except RecursionError:
                    flag(r, "R2", "formula: parentheses nest too deeply")
                except ValueError as e:
                    flag(r, "R2", f"formula: {e}")

    for rid, tree in list(trees.items()):
        unknown = sorted(n for n in names(tree) if n not in by_id)
        if unknown:
            flag(by_id[rid], "R2", f"formula names {', '.join(unknown)}, not in the register")
            del trees[rid]

    for r in rows:
        if r["kind"] == "candidate" and r["of"]:
            target = by_id.get(r["of"])
            if target is None or target["kind"] not in ("input", "derived") or target["_value"] is None:
                flag(r, "R5", f"of {r['of']!r} is not an input or derived row with a value")

    # Order the rows so that each comes after the rows it names (no recursion).
    deps = {rid: sorted(n for n in names(t) if n in trees) for rid, t in trees.items()}
    order, color, looped = [], {}, set()
    for root in trees:
        if color.get(root):
            continue
        color[root], path, todo = "grey", [root], [iter(deps[root])]
        while todo:
            child = next(todo[-1], None)
            if child is None:
                todo.pop()
                node = path.pop()
                color[node] = "black"
                order.append(node)
            elif color.get(child) == "grey":
                looped.update(path[path.index(child):])
            elif not color.get(child):
                color[child] = "grey"
                path.append(child)
                todo.append(iter(deps[child]))
    for rid in trees:
        if rid in looped:
            flag(by_id[rid], "R3", "formula refers back to this row")

    results, state = {}, {}  # state: "skip" (register problem upstream) or ("open", name)

    def value_of(name):
        r = by_id[name]
        if r["kind"] == "placeholder":
            raise _Open(name)
        if r["kind"] == "input":
            if r["_value"] is None:
                raise _Skip()
            return r["_value"]
        if name in results:
            return results[name]
        st = state.get(name, "skip")
        if st == "skip":
            raise _Skip()
        raise _Open(st[1])

    for rid in order:
        if rid in looped:
            state[rid] = "skip"
            continue
        try:
            results[rid] = evaluate(trees[rid], value_of)
        except _Open as e:
            state[rid] = ("open", e.name)
        except _Skip:
            state[rid] = "skip"
        except ZeroDivisionError:
            flag(by_id[rid], "R2", "formula divides by zero")
            state[rid] = "skip"
        except TooLarge as e:
            flag(by_id[rid], "R2", str(e))
            state[rid] = "skip"
        if state.get(rid, None) not in (None, "skip") and rid not in bad:
            r = by_id[rid]
            findings.append((r["_line"], rid, "UNRESOLVED", f"needs {state[rid][1]}, which has no value"))

    for rid in trees:
        r = by_id[rid]
        if r["kind"] == "derived" and rid in results and r["_value"] is not None and r["_places"] is not None:
            v = results[rid]
            if not matches(v, r["_value"], r["_places"]):
                findings.append((r["_line"], rid, "MISMATCH",
                                 f"shown {r['shown']} ({r['value']}); formula gives {fmt(v)}"))

    for target in rows:
        cands = [c for c in rows if c["kind"] == "candidate" and c["of"] == target["id"] and target["id"]]
        if not cands or target["_value"] is None or target["_places"] is None:
            continue
        got = [c for c in cands if c["id"] in results
               and matches(results[c["id"]], target["_value"], target["_places"])]
        tried = [c for c in cands if c["id"] in results or isinstance(state.get(c["id"]), tuple)]
        if not got and tried:
            done = [f"{c['id']}={fmt(results[c['id']])}" for c in cands if c["id"] in results]
            findings.append((target["_line"], target["id"], "NOREPRO",
                             f"shown {target['shown']} ({target['value']}); no candidate gives it"
                             + (f": {', '.join(done)}" if done else "")))
    return issues, findings, results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("register")
    ap.add_argument("--quiet", action="store_true", help="print only the summary")
    args = ap.parse_args(argv)
    try:
        rows = load(args.register)
    except (OSError, ValueError, UnicodeDecodeError) as e:
        print(f"calccheck: {args.register}: {e}" if isinstance(e, UnicodeDecodeError) else f"calccheck: {e}",
              file=sys.stderr)
        return 2
    issues, findings, results = check(rows)
    by_id = {r["id"]: r for r in rows}
    if not args.quiet:
        for line, rid, code, msg in sorted(issues + findings, key=lambda x: x[0]):
            print(f"{code}\tline {line}\tid {rid}\t{msg}")
        for r in rows:
            if r["kind"] == "candidate" and r["id"] in results:
                t = by_id.get(r["of"])
                ok = (t is not None and t.get("_value") is not None and t.get("_places") is not None
                      and matches(results[r["id"]], t["_value"], t["_places"]))
                print(f"candidate\t{r['id']}\tof {r['of']}\t{fmt(results[r['id']])}\t{'gives it' if ok else 'does not'}")
    kinds = {k: sum(r["kind"] == k for r in rows) for k in KINDS}
    codes = [c for _, _, c, _ in findings]
    print(f"rows: {len(rows)}")
    print("kind: " + "  ".join(f"{k} {n}" for k, n in kinds.items()))
    print(f"findings: MISMATCH {codes.count('MISMATCH')}  NOREPRO {codes.count('NOREPRO')}  "
          f"UNRESOLVED {codes.count('UNRESOLVED')}")
    print(f"issues: {len(issues)}")
    return 1 if issues or findings else 0


if __name__ == "__main__":
    sys.exit(main())
