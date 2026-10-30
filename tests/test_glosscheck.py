"""Tests for glosscheck.py, on a synthetic glossary and texts written for these tests."""
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

import glosscheck  # noqa: E402

GLOSSARY = (
    "id\tja\ten\tvariants\tavoid\tnote\n"
    "t1\t予兆管理\tYochō Kanri\t-\tPredictive Management\tthe method's name\n"
    "t2\t予知保全\tpredictive maintenance\t-\t-\ta general term\n"
    "t3\t計画外停止\tunplanned stoppage\tunplanned downtime\t-\tseries wording\n"
    "t4\t回収期間\tpayback period | payback\t-\t-\ttwo accepted forms\n"
)


class GlosscheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.gloss = self.write("g.tsv", GLOSSARY)

    def write(self, name, text):
        p = os.path.join(self.tmp, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def run_tool(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = glosscheck.main(list(args))
        return rc, out.getvalue(), err.getvalue()

    def codes(self, en, ja=None):
        rows = glosscheck.load(self.gloss)
        return [c for _, _, c, _ in glosscheck.check_text(rows, en, ja)]

    def test_clean(self):
        self.assertEqual(self.codes("Yochō Kanri cut unplanned stoppages; the payback period is 2 years."), [])

    def test_avoid_and_variant(self):
        self.assertEqual(self.codes("Predictive Management"), ["AVOID"])
        self.assertEqual(self.codes("unplanned downtime fell"), ["VARIANT"])

    def test_case_and_words(self):
        # a form with a capital letter is case-sensitive; others are not
        self.assertEqual(self.codes("predictive management"), [])
        self.assertEqual(self.codes("Unplanned Downtime"), ["VARIANT"])
        # whole words only
        self.assertEqual(self.codes("unplanned downtimes"), ["VARIANT"])
        self.assertEqual(self.codes("unplanned downtimesx"), [])
        self.assertEqual(self.codes("xunplanned downtime"), [])

    def test_pair_missing(self):
        self.assertEqual(self.codes("Nothing here.", "回収期間は2年"), ["MISSING"])
        self.assertEqual(self.codes("The payback is 2 years.", "回収期間は2年"), [])
        # a variant counts as present for MISSING, and is reported as a variant
        self.assertEqual(self.codes("unplanned downtime", "計画外停止"), ["VARIANT"])
        # a term absent from the Japanese is not required
        self.assertEqual(self.codes("Nothing here.", "別の文"), [])

    def test_line_numbers(self):
        rows = glosscheck.load(self.gloss)
        found = glosscheck.check_text(rows, "a\nb\nunplanned downtime\n")
        self.assertEqual(found[0][0], 3)

    def test_glossary_problems(self):
        bad = self.write("bad.tsv", GLOSSARY + "t1\t別\tx | x\t-\t-\t\n")
        rows = glosscheck.load(bad)
        codes = sorted(c for _, _, c, _ in glosscheck.check_glossary(rows))
        self.assertEqual(codes, ["G1", "G2", "G3"])

    def test_main(self):
        en = self.write("en.md", "Predictive Management\n")
        ja = self.write("ja.md", "回収期間\n")
        rc, out, _ = self.run_tool(self.gloss, en, "--pair", f"{ja}={en}")
        self.assertEqual(rc, 1)
        self.assertIn("findings: AVOID 2  VARIANT 0  MISSING 1", out)
        ok = self.write("ok.md", "Yochō Kanri\n")
        self.assertEqual(self.run_tool(self.gloss, ok, "--quiet")[0], 0)

    def test_bad_input(self):
        en = self.write("en.md", "x\n")
        for gl in ("", "id\tja\n", "id\tja\ten\tvariants\tavoid\tnote\nt1\tx\n"):
            p = self.write("g2.tsv", gl)
            self.assertEqual(self.run_tool(p, en)[0], 2, gl)
        self.assertEqual(self.run_tool(self.gloss)[0], 2)
        self.assertEqual(self.run_tool(self.gloss, "--pair", "nopair")[0], 2)
        self.assertEqual(self.run_tool(self.gloss, os.path.join(self.tmp, "none.md"))[0], 2)

    def test_series_glossary_is_clean(self):
        path = os.path.join(HERE, "..", "register", "glossary_series.tsv")
        self.assertEqual(glosscheck.check_glossary(glosscheck.load(path)), [])


if __name__ == "__main__":
    unittest.main()
