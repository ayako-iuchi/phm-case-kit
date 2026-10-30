"""Tests for briefcheck.py, on synthetic briefs written for these tests."""
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

import briefcheck  # noqa: E402

GOOD = """# 提案

2026年10月30日時点

<!-- comment with 1 number -->
- 架空事例では、停止時間が約180時間から約32時間に減った [2]
- 「原文をそのまま」（第8回）[1]
- 判断の前に、記録を集める。

## 出典

1. 著者「題」第8回、2026年10月28日に保存
2. 事例の題（架空の事例）2026年5月21日
"""


class BriefcheckTest(unittest.TestCase):
    def codes(self, text, **kw):
        return [c for _, c, _ in briefcheck.check(text, **kw)[2]]

    def test_good(self):
        self.assertEqual(self.codes(GOOD), [])

    def test_each_check(self):
        self.assertIn("B1", self.codes(GOOD.replace("- 判断の前に、記録を集める。", "- 3件を集める。")))
        self.assertIn("B1", self.codes(GOOD.replace("- 判断の前に、記録を集める。", "- 「引用」を集める。")))
        self.assertIn("B2", self.codes(GOOD.replace("（第8回）[1]", "（第8回）[1, 3]")))
        self.assertIn("B3", self.codes(GOOD + "3. 使わない資料 2026年1月\n"))
        self.assertIn("B4", self.codes(GOOD.replace("架空事例では、", "")))
        self.assertIn("B5", self.codes(GOOD.replace("2026年5月21日", "")))
        self.assertIn("B6", self.codes(GOOD, max_chars=10))

    def test_markers_and_dates(self):
        self.assertEqual(briefcheck.cited("a ［1］ b [2，3]"), [1, 2, 3])
        self.assertEqual(self.codes(GOOD.replace("2026年10月30日時点", "As of 30 October 2026")), [])
        for d in ("2026年10月", "2026-10-30", "30 October 2026", "October 2026"):
            self.assertNotIn("B5", self.codes(GOOD.replace("2026年5月21日", d)), d)

    def test_bad_input(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        p = os.path.join(tmp, "b.md")
        for text in ("# 題\n\n- 文 [1]\n", GOOD + "1. 二重 2026年1月\n"):
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(briefcheck.main([p]), 2)
        with open(p, "w", encoding="utf-8-sig") as f:
            f.write(GOOD)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(briefcheck.main([p, "--quiet"]), 0)
        self.assertIn("issues: B1 0  B2 0  B3 0  B4 0  B5 0  B6 0", out.getvalue())


if __name__ == "__main__":
    unittest.main()
