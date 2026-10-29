"""Tests for datecheck.py, on a synthetic register written for these tests."""
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

import datecheck  # noqa: E402

HEADER = "\t".join(datecheck.REQUIRED)


def row(**kw):
    base = {"id": "d1", "document": "Doc", "page": "3", "statement": "s", "doc_date": "2026-05-21",
            "event": "measure abolished", "event_date": "2025-03-31", "status_then": "true",
            "status_now": "true", "source_title": "Ministry page", "url": "https://example.org/a",
            "accessed": "2026-10-29", "recheck_by": "2027-04-30", "class": "CURRENT", "note": ""}
    base.update(kw)
    return "\t".join(base[k] for k in datecheck.REQUIRED)


class DatecheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.as_of = dt.date(2026, 10, 29)

    def reg(self, *lines, name="r.tsv", encoding="utf-8", nl="\n"):
        p = os.path.join(self.tmp, name)
        with open(p, "w", encoding=encoding, newline="") as f:
            f.write(HEADER + nl + nl.join(lines) + nl)
        return p

    def codes(self, *lines):
        return [c for _, _, c, _ in datecheck.check(datecheck.load(self.reg(*lines)), self.as_of)]

    def test_clean(self):
        self.assertEqual(self.codes(
            row(),
            row(id="d2", event_date="2026-05-29", status_now="false", **{"class": "STALE", "note": "new edition"}),
            row(id="d3", event_date="2019-04", status_then="false", status_now="false",
                **{"class": "WRONG-THEN", "note": "applied since 2019"}),
            row(id="d4", event_date="-", **{"class": "UNDATED", "note": "no version given"}),
            row(id="d5", status_then="unknown", status_now="unknown", url="", accessed="",
                **{"class": "CANNOT", "note": "statute not opened"}),
            row(id="d6", doc_date="<=2026-08-25"),
        ), [])

    def test_required_and_values(self):
        self.assertIn("T1", self.codes(row(statement="")))
        self.assertIn("T1", self.codes(row(**{"class": "STALE", "note": ""}, status_now="false",
                                           event_date="2026-06")))
        self.assertIn("T2", self.codes(row(**{"class": "OLD"})))
        self.assertIn("T2", self.codes(row(status_now="yes")))
        self.assertIn("T2", self.codes(row(doc_date="2026/05/21")))
        self.assertIn("T2", self.codes(row(event_date="spring 2025")))
        self.assertIn("T2", self.codes(row(recheck_by="20270430")))

    def test_class_and_status(self):
        self.assertIn("T3", self.codes(row(status_now="false")))
        self.assertIn("T3", self.codes(row(**{"class": "WRONG-THEN", "note": "n"})))
        self.assertIn("T3", self.codes(row(**{"class": "CANNOT", "note": "n"})))

    def test_hindsight(self):
        later = row(event_date="2026-06-30", status_then="false", status_now="false",
                    **{"class": "WRONG-THEN", "note": "n"})
        self.assertIn("T4", self.codes(later))
        before = row(event_date="2026-05-01", status_now="false", **{"class": "STALE", "note": "n"})
        self.assertIn("T4", self.codes(before))
        same_month = row(event_date="2026-05", status_now="false", **{"class": "STALE", "note": "n"})
        self.assertNotIn("T4", self.codes(same_month))
        bound = row(doc_date="<=2026-08-25", event_date="2026-06", status_now="false",
                    **{"class": "STALE", "note": "n"})
        self.assertNotIn("T4", self.codes(bound))

    def test_accessed_and_recheck(self):
        self.assertIn("T5", self.codes(row(accessed="")))
        self.assertIn("T5", self.codes(row(accessed="2026-11-01")))
        self.assertIn("T7", self.codes(row(recheck_by="2026-10-29")))
        self.assertNotIn("T7", self.codes(row(recheck_by="2026-10-30")))
        self.assertIn("T6", self.codes(row(), row()))

    def test_main(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = datecheck.main([self.reg(row(), row(id="d2", recheck_by="2026-12-01")), "--as-of", "2026-10-29"])
        self.assertEqual(code, 0)
        self.assertIn("class: CURRENT 2  STALE 0  WRONG-THEN 0  UNDATED 0  CANNOT 0", out.getvalue())
        self.assertIn("next recheck: 2026-12-01", out.getvalue())
        with redirect_stdout(io.StringIO()):
            self.assertEqual(datecheck.main([self.reg(row(recheck_by="2026-01-01")), "--as-of", "2026-10-29"]), 1)

    def test_bad_input(self):
        p = os.path.join(self.tmp, "b.tsv")
        for text in ("id\tclass\nx\tCURRENT\n", HEADER + "\n", HEADER + "\n" + row() + "\textra\n",
                     HEADER + "\tid\n" + row() + "\tx\n", HEADER + "\n" + row(note="x" * 200000) + "\n"):
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(datecheck.main([p]), 2, text[:60])
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(datecheck.main([self.reg(row()), "--as-of", "20261029"]), 2)

    def test_bom_and_crlf(self):
        p = self.reg(row(), encoding="utf-8-sig", nl="\r\n")
        self.assertEqual(datecheck.check(datecheck.load(p), self.as_of), [])


if __name__ == "__main__":
    unittest.main()
