"""Tests for calccheck.py, on a synthetic register written for these tests."""
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

import calccheck  # noqa: E402

HEADER = "\t".join(calccheck.REQUIRED)


def row(**kw):
    base = {"id": "a", "document": "Doc", "page": "1", "label": "x", "shown": "[2]", "value": "2",
            "places": "0", "kind": "input", "formula": "", "of": "", "note": ""}
    base.update(kw)
    return "\t".join(base[k] for k in calccheck.REQUIRED)


class CalccheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def reg(self, *lines, encoding="utf-8", nl="\n"):
        p = os.path.join(self.tmp, "r.tsv")
        with open(p, "w", encoding=encoding, newline="") as f:
            f.write(HEADER + nl + nl.join(lines) + nl)
        return p

    def run_check(self, *lines):
        issues, findings, results = calccheck.check(calccheck.load(self.reg(*lines)))
        return [c for _, _, c, _ in issues], [c for _, _, c, _ in findings], results

    def test_parse_and_evaluate(self):
        t = calccheck.parse("a + b * (2 - c) / 4")
        self.assertEqual(calccheck.names(t), {"a", "b", "c"})
        env = {"a": Fraction(1), "b": Fraction(2), "c": Fraction(1)}.__getitem__
        self.assertEqual(calccheck.evaluate(t, env), Fraction(3, 2))
        self.assertEqual(calccheck.evaluate(calccheck.parse("-1 - -2"), env), 1)
        self.assertEqual(calccheck.evaluate(calccheck.parse("0.1 + 0.2"), env), Fraction(3, 10))
        for bad in ("a +", "(a", "a b", "a ** 2", "__import__('os')", "", "1e3"):
            with self.assertRaises(ValueError, msg=bad):
                calccheck.parse(bad)

    def test_matches_at_shown_places(self):
        self.assertTrue(calccheck.matches(Fraction("1.45"), Fraction("1.5"), 1))
        self.assertTrue(calccheck.matches(Fraction("1.55"), Fraction("1.5"), 1))
        self.assertFalse(calccheck.matches(Fraction("1.5501"), Fraction("1.5"), 1))
        self.assertTrue(calccheck.matches(Fraction("0.996"), Fraction("1.0"), 1))
        self.assertFalse(calccheck.matches(Fraction("2.965"), Fraction("3.32"), 2))

    def test_clean(self):
        issues, findings, results = self.run_check(
            row(),
            row(id="b", shown="3", value="3"),
            row(id="t", shown="約5", value="5", kind="derived", formula="a + b"),
            row(id="x", shown="[X]", value="-", places="-", kind="placeholder"),
            row(id="c1", shown="-", value="-", places="-", kind="candidate", formula="b + 2", of="t"),
            row(id="c2", shown="-", value="-", places="-", kind="candidate", formula="a * 2", of="t"),
        )
        self.assertEqual((issues, findings), ([], []))
        self.assertEqual(results["t"], 5)

    def test_findings(self):
        _, findings, _ = self.run_check(
            row(), row(id="b", value="3", shown="3"),
            row(id="t", shown="約6", value="6", kind="derived", formula="a + b"),
            row(id="x", shown="[X]", value="-", places="-", kind="placeholder"),
            row(id="u", shown="1", value="1", kind="derived", formula="x * a"),
            row(id="p", shown="[1.5]", value="1.5", places="1"),
            row(id="c1", shown="-", value="-", places="-", kind="candidate", formula="b * a", of="p"),
            row(id="c2", shown="-", value="-", places="-", kind="candidate", formula="b / 3", of="p"),
            row(id="c3", shown="-", value="-", places="-", kind="candidate", formula="x / a", of="p"),
        )
        self.assertEqual(sorted(findings), ["MISMATCH", "NOREPRO", "UNRESOLVED", "UNRESOLVED"])

    def test_candidate_that_gives_it_clears_norepro(self):
        _, findings, _ = self.run_check(
            row(), row(id="p", shown="[1.5]", value="1.5", places="1"),
            row(id="c1", shown="-", value="-", places="-", kind="candidate", formula="a * 0.75", of="p"),
            row(id="c2", shown="-", value="-", places="-", kind="candidate", formula="a", of="p"),
        )
        self.assertEqual(findings, [])

    def test_register_problems(self):
        self.assertIn("R1", self.run_check(row(id="1a"))[0])
        self.assertIn("R1", self.run_check(row(kind="sum"))[0])
        self.assertIn("R1", self.run_check(row(value="2,0"))[0])
        self.assertIn("R1", self.run_check(row(places="x"))[0])
        self.assertIn("R1", self.run_check(row(formula="1"))[0])
        self.assertIn("R1", self.run_check(row(kind="derived"))[0])
        self.assertIn("R1", self.run_check(row(kind="placeholder", value="2", places="-"))[0])
        self.assertIn("R1", self.run_check(row(), row(id="c", kind="candidate", formula="a", value="-", places="-"))[0])
        self.assertIn("R1", self.run_check(row(of="a"))[0])
        self.assertIn("R2", self.run_check(row(id="t", kind="derived", formula="a +"))[0])
        self.assertIn("R2", self.run_check(row(id="t", kind="derived", formula="zz + 1"))[0])
        self.assertIn("R2", self.run_check(row(), row(id="t", kind="derived", formula="a / 0"))[0])
        self.assertIn("R3", self.run_check(row(id="t", kind="derived", formula="u"),
                                           row(id="u", kind="derived", formula="t"))[0])
        self.assertIn("R4", self.run_check(row(), row())[0])
        self.assertIn("R5", self.run_check(
            row(id="x", shown="[X]", value="-", places="-", kind="placeholder"),
            row(id="c", shown="-", value="-", places="-", kind="candidate", formula="1", of="x"))[0])
        self.assertIn("R5", self.run_check(
            row(id="c", shown="-", value="-", places="-", kind="candidate", formula="1", of="nope"))[0])

    def test_main(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = calccheck.main([self.reg(row(), row(id="t", shown="4", value="4", kind="derived", formula="a * 2"))])
        self.assertEqual(code, 0)
        self.assertIn("kind: input 1  derived 1  candidate 0  placeholder 0", out.getvalue())
        self.assertIn("findings: MISMATCH 0  NOREPRO 0  UNRESOLVED 0", out.getvalue())
        self.assertIn("issues: 0", out.getvalue())
        with redirect_stdout(io.StringIO()):
            self.assertEqual(calccheck.main([self.reg(row(), row(id="t", shown="5", value="5", kind="derived",
                                                                 formula="a * 2"))]), 1)

    def test_bad_input(self):
        p = os.path.join(self.tmp, "b.tsv")
        for text in ("id\tkind\nx\tinput\n", HEADER + "\n", HEADER + "\n" + row() + "\textra\n",
                     HEADER + "\tid\n" + row() + "\tx\n", HEADER + "\n" + row(note="x" * 200000) + "\n"):
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(calccheck.main([p]), 2, text[:60])

    def test_bom_and_crlf(self):
        p = self.reg(row(), encoding="utf-8-sig", nl="\r\n")
        self.assertEqual(calccheck.check(calccheck.load(p))[:2], ([], []))

    def test_robustness(self):
        cand = dict(shown="-", value="-", places="-")
        self.assertIn("R1", self.run_check(row(id="", kind="derived", formula="1 + 1"))[0])
        issues, findings, _ = self.run_check(row(id="t", kind="derived", formula="u"),
                                             row(id="u", kind="derived", formula="t"),
                                             row(id="w", kind="derived", formula="t + 1"))
        self.assertEqual((sorted(issues), findings), (["R3", "R3"], []))
        issues, findings, _ = self.run_check(row(), row(id="z", kind="derived", formula="a / (a - a)"),
                                             row(id="w", kind="derived", formula="z + 1"))
        self.assertEqual((issues, findings), (["R2"], []))
        issues, findings, _ = self.run_check(row(value="x"), row(id="w", kind="derived", formula="a + 1"))
        self.assertEqual((issues, findings), (["R1"], []))
        self.assertIn("R2", self.run_check(row(id="t", kind="derived", formula="(" * 5000 + "1" + ")" * 5000))[0])
        self.assertIn("R2", self.run_check(row(id="t", kind="derived", formula="(" * 900 + "1" + ")" * 900))[0])
        self.assertIn("R1", self.run_check(row(places="20000000"))[0])
        self.assertIn("R1", self.run_check(row(value="9" * 5000))[0])
        chain = [row(id="c0")] + [row(id=f"c{i}", kind="derived", formula=f"c{i - 1} * 10") for i in range(1, 3000)]
        issues, _, _ = self.run_check(*chain)
        self.assertTrue(set(issues) <= {"R2"})
        self.assertEqual(calccheck.fmt(Fraction(10) ** 400 / 3, 2)[-3:], ".33")
        self.assertEqual(calccheck.fmt(Fraction(-1, 3)), "-0.3333")

    def test_derived_reference_and_propagation(self):
        _, findings, results = self.run_check(
            row(), row(id="t", shown="9", value="9", kind="derived", formula="a + 1"),
            row(id="u", shown="6", value="6", kind="derived", formula="t * 2"),
            row(id="x", shown="-", value="-", places="-", kind="placeholder"),
            row(id="v", shown="1", value="1", kind="derived", formula="x + 1"),
            row(id="w", shown="1", value="1", kind="derived", formula="v + 1"))
        self.assertEqual(results["u"], 6)
        self.assertEqual(sorted(findings), ["MISMATCH", "UNRESOLVED", "UNRESOLVED"])

    def test_quiet_and_files(self):
        out = io.StringIO()
        with redirect_stdout(out):
            calccheck.main([self.reg(row(), row(id="t", shown="5", value="5", kind="derived", formula="a * 2")), "--quiet"])
        self.assertNotIn("MISMATCH\tline", out.getvalue())
        self.assertIn("findings: MISMATCH 1", out.getvalue())
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(calccheck.main([os.path.join(self.tmp, "none.tsv")]), 2)
            self.assertEqual(calccheck.main([self.reg(row(), encoding="utf-16")]), 2)


if __name__ == "__main__":
    unittest.main()
