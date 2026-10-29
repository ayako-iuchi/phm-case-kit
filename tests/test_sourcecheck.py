"""Tests for sourcecheck.py, on a synthetic register written for these tests."""
import datetime as dt
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

import sourcecheck  # noqa: E402

HEADER = "\t".join(sourcecheck.REQUIRED)


def row(**kw):
    base = {"id": "x1", "document": "Doc", "page": "3", "statement": "s", "cited_ref": "-",
            "source_kind": "primary", "source_title": "White paper", "issuer": "Ministry",
            "edition": "2025", "url": "https://example.org/a", "location": "p.21",
            "underlying": "Survey", "accessed": "2026-10-29", "class": "A", "note": ""}
    base.update(kw)
    return "\t".join(base[k] for k in sourcecheck.REQUIRED)


class SourcecheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.as_of = dt.date(2026, 10, 29)

    def reg(self, *lines):
        p = os.path.join(self.tmp, "r.tsv")
        with open(p, "w", encoding="utf-8") as f:
            f.write(HEADER + "\n" + "\n".join(lines) + "\n")
        return p

    def codes(self, *lines):
        rows = sourcecheck.load(self.reg(*lines))
        return [c for _, _, c, _ in sourcecheck.check(rows, self.as_of)]

    def test_clean_rows(self):
        self.assertEqual(self.codes(
            row(),
            row(id="x2", **{"class": "B", "note": "year dropped"}),
            row(id="x3", source_kind="secondary", source_title="A column", location="", underlying="-",
                **{"class": "C", "note": "no primary located"}),
            row(id="x4", source_kind="none", source_title="", issuer="", edition="", url="", location="",
                underlying="-", accessed="", **{"class": "E", "note": "quotation with no source"}),
        ), [])

    def test_required_and_notes(self):
        self.assertIn("R1", self.codes(row(statement="")))
        self.assertIn("R1", self.codes(row(**{"class": "B", "note": ""})))
        self.assertIn("R1", self.codes(row(**{"class": "D", "note": ""})))

    def test_allowed_values(self):
        self.assertIn("R2", self.codes(row(**{"class": "F"})))
        self.assertIn("R2", self.codes(row(**{"class": "AB"})))
        self.assertIn("R2", self.codes(row(source_kind="tertiary")))

    def test_primary_needed(self):
        self.assertIn("R3", self.codes(row(source_kind="secondary")))
        self.assertIn("R3", self.codes(row(location="")))
        self.assertIn("R3", self.codes(row(**{"class": "D", "note": "differs"}, source_title="")))

    def test_secondary_for_c(self):
        self.assertIn("R4", self.codes(row(**{"class": "C", "note": "n"})))  # primary kind
        self.assertIn("R4", self.codes(row(source_kind="secondary", source_title="", **{"class": "C", "note": "n"})))

    def test_accessed(self):
        self.assertIn("R5", self.codes(row(accessed="")))
        self.assertIn("R5", self.codes(row(accessed="29/10/2026")))
        self.assertIn("R5", self.codes(row(accessed="2026-10-30")))
        self.assertEqual(self.codes(row(url="", accessed="")), [])

    def test_duplicate_and_e(self):
        self.assertIn("R6", self.codes(row(), row()))
        self.assertIn("R7", self.codes(row(**{"class": "E", "note": "n"})))

    def test_dates_strict(self):
        self.assertIn("R5", self.codes(row(accessed="20261029")))
        self.assertIn("R5", self.codes(row(accessed="2026-W44-4")))
        self.assertIn("R5", self.codes(row(url="", accessed="garbage")))
        self.assertIn("R5", self.codes(row(url="", accessed="2099-01-01")))
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(sourcecheck.main([self.reg(row()), "--as-of", "20261029"]), 2)

    def test_e_has_no_source(self):
        e = dict(source_kind="none", source_title="", issuer="", edition="", url="", location="",
                 underlying="-", accessed="", **{"class": "E", "note": "n"})
        self.assertEqual(self.codes(row(**e)), [])
        for k, v in (("url", "https://example.org/x"), ("source_title", "T"), ("location", "p.1")):
            self.assertIn("R7", self.codes(row(**{**e, k: v, "accessed": "2026-10-29"})), k)

    def test_bom_and_crlf(self):
        p = os.path.join(self.tmp, "b.tsv")
        with open(p, "w", encoding="utf-8-sig", newline="") as f:
            f.write(HEADER + "\r\n" + row() + "\r\n")
        self.assertEqual(sourcecheck.check(sourcecheck.load(p), self.as_of), [])

    def test_summary_and_exit(self):
        p = self.reg(row(), row(id="x2", **{"class": "B", "note": "n"}))
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = sourcecheck.main([p, "--as-of", "2026-10-29"])
        self.assertEqual(code, 0)
        self.assertIn("class: A 1  B 1  C 0  D 0  E 0", buf.getvalue())
        self.assertIn("source: primary 2  secondary 0  none 0", buf.getvalue())
        bad = self.reg(row(**{"class": "Z"}))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(sourcecheck.main([bad, "--as-of", "2026-10-29"]), 1)

    def test_bad_input(self):
        p = os.path.join(self.tmp, "h.tsv")
        for text in ("id\tclass\nx\tA\n", HEADER + "\n", HEADER + "\n" + row() + "\textra\n"):
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(sourcecheck.main([p]), 2, text)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(sourcecheck.main([self.reg(row()), "--as-of", "soon"]), 2)
        with open(p, "w", encoding="utf-8") as f:
            f.write(HEADER + "\tid\n" + row() + "\tx2\n")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(sourcecheck.main([p]), 2)
        with open(p, "w", encoding="utf-8") as f:
            f.write(HEADER + "\n" + row(statement="x" * 200000) + "\n")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(sourcecheck.main([p]), 2)


if __name__ == "__main__":
    unittest.main()
