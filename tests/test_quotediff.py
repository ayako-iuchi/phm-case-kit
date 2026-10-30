"""Tests for quotediff.py, on a synthetic source written for these tests."""
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

import quotediff  # noqa: E402

SOURCE = (
    "架空の工場では、設備の状態を毎日見ています。\n"
    "保全の担当者は「止まる前に手を打つ」と\n話しました。\n"
    "\f"
    "二つ目の頁です。ＡＢＣ社の計画は三年で終わります。\n"
    "現場の声を聞くことが、最初の一歩でした。\n"
    "\f"
)
HEADER = "\t".join(quotediff.REQUIRED)


def row(**kw):
    base = {"id": "q1", "document": "Doc", "page": "1", "source": "S",
            "quote": "止まる前に手を打つ", "marked": "none", "note": ""}
    base.update(kw)
    return "\t".join(base[k] for k in quotediff.REQUIRED)


class QuotediffTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.src = os.path.join(self.tmp, "s.txt")
        with open(self.src, "w", encoding="utf-8") as f:
            f.write(SOURCE)

    def reg(self, *lines):
        p = os.path.join(self.tmp, "r.tsv")
        with open(p, "w", encoding="utf-8") as f:
            f.write(HEADER + "\n" + "\n".join(lines) + "\n")
        return p

    def run_main(self, *lines, extra=()):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = quotediff.main([self.reg(*lines), "--text", f"S={self.src}", *extra])
        return code, out.getvalue()

    def classes(self, *lines):
        sources = {"S": quotediff.Source(quotediff.read_pages(self.src, header_lines=0))}
        issues, results = quotediff.check(quotediff.load(self.reg(*lines)), sources)
        return [c for _, _, c, _ in issues], [(c, d) for _, _, c, d in results]

    def test_exact_across_lines_and_width(self):
        _, res = self.classes(row(quote="と話しました"), row(id="q2", quote="ABC社の計画は三年で終わります"))
        self.assertEqual([c for c, _ in res], ["EXACT", "EXACT"])
        self.assertIn("p.2", res[1][1])

    def test_ellipsis(self):
        _, res = self.classes(row(quote="ABC社の計画は…終わります", marked="ellipsis"),
                              row(id="q2", quote="終わります…ABC社", marked="ellipsis"))
        self.assertEqual(res[0][0], "ELLIPSIS")
        self.assertNotEqual(res[1][0], "ELLIPSIS")

    def test_altered_lists_changes(self):
        _, res = self.classes(row(quote="現場の声を聴くことが、最初の大きな一歩でした"))
        cls, detail = res[0]
        self.assertEqual(cls, "ALTERED")
        self.assertIn("replaced «聞» with «聴»", detail)
        self.assertIn("added «大きな»", detail)
        self.assertIn("p.2", detail)
        _, res = self.classes(row(quote="現場の声を聞くことが一歩でした"))
        self.assertIn("omitted", res[0][1])

    def test_not_found_and_paraphrase(self):
        _, res = self.classes(row(quote="まったく関係のない別の文章をここに書きます"),
                              row(id="q2", quote="現場の声を聴くことが最初でした", marked="paraphrase"))
        self.assertEqual([c for c, _ in res], ["NOT-FOUND", "PARAPHRASE"])

    def test_register_problems(self):
        self.assertIn("Q1", self.classes(row(quote=""))[0])
        self.assertIn("Q1", self.classes(row(marked="summary"))[0])
        self.assertIn("Q2", self.classes(row(source="T"))[0])
        self.assertIn("Q3", self.classes(row(), row())[0])

    def test_main(self):
        code, out = self.run_main(row())
        self.assertEqual(code, 0)
        self.assertIn("class: EXACT 1  ELLIPSIS 0  PARAPHRASE 0  ALTERED 0  NOT-FOUND 0", out)
        code, out = self.run_main(row(quote="止まる前に手を打った"))
        self.assertEqual(code, 1)
        code, _ = self.run_main(row(), extra=("--min-ratio", "2"))
        self.assertEqual(code, 2)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(quotediff.main([self.reg(row()), "--text", "nopath"]), 2)
            self.assertEqual(quotediff.main([self.reg(row()), "--text", f"S={self.src}", "--text", f"S={self.src}"]), 2)


if __name__ == "__main__":
    unittest.main()
