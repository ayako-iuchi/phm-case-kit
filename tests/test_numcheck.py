"""Tests for numcheck.py, on a synthetic register and synthetic texts written for these tests."""
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

import numcheck  # noqa: E402

HEADER = "\t".join(numcheck.REQUIRED)


def row(**kw):
    base = {"id": "n1", "value": "82%", "document": "A", "page": "1", "quote": "",
            "measures": "stoppage time reduction", "unit": "time", "base": "before",
            "period": "-", "placeholder": "no", "note": ""}
    base.update(kw)
    return "\t".join(base[k] for k in numcheck.REQUIRED)


class NumcheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def write(self, name, text, encoding="utf-8"):
        p = os.path.join(self.tmp, name)
        with open(p, "w", encoding=encoding, newline="") as f:
            f.write(text)
        return p

    def reg(self, *lines):
        return self.write("r.tsv", HEADER + "\n" + "\n".join(lines) + "\n")

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = numcheck.main(list(args))
        return code, out.getvalue()

    def test_same_definition_is_clean(self):
        code, out = self.run_main(self.reg(row(), row(id="n2", document="B")))
        self.assertEqual(code, 0)
        self.assertIn("drift: 0  conflict: 0", out)

    def test_drift_and_conflict(self):
        p = self.reg(row(), row(id="n2", document="B", measures="stoppage count", unit="count"),
                     row(id="n3", document="C", value="80%"))
        code, out = self.run_main(p)
        self.assertEqual(code, 0)  # findings, not failures
        self.assertIn("DRIFT\t82%\t2 definitions in 2 rows", out)
        self.assertIn("CONFLICT", out)
        self.assertIn("values 80%, 82%", out)
        code, _ = self.run_main(p, "--strict")
        self.assertEqual(code, 1)

    def test_fullwidth_value_groups_with_halfwidth(self):
        code, out = self.run_main(self.reg(row(), row(id="n2", value="８２％", document="B", unit="count")))
        self.assertIn("drift: 1", out)

    def test_quote_and_missed(self):
        text = self.write("a.txt", "停止時間を\n82%削減した。\f別の頁 [82]% と 182% と ８２％\f")
        ok = self.reg(row(quote="停止時間を82%削減"), row(id="n2", page="2"), row(id="n3", page="2"))
        code, out = self.run_main(ok, "--text", f"A={text}")
        self.assertEqual(code, 0, out)
        self.assertIn("quote: 0  missed: 0", out)
        missed = self.reg(row(quote="停止時間を82%削減"), row(id="n2", page="2"))
        code, out = self.run_main(missed, "--text", f"A={text}")
        self.assertEqual(code, 1)
        self.assertIn("MISSED\tA p.2: 82% occurs 2 times, register has 1", out)
        wrong = self.reg(row(quote="停止時間を82%削減", page="2"), row(id="n2", page="2"), row(id="n3", page="1"))
        code, out = self.run_main(wrong, "--text", f"A={text}")
        self.assertEqual(code, 1)
        self.assertIn("QUOTE", out)

    def test_value_pattern(self):
        pat = numcheck.value_pattern("1.5年")
        self.assertEqual(len(pat.findall("ROI1.5年、11.5年、1.5年回収、[1.5]年")), 3)
        self.assertEqual(numcheck.split_value("8〜12回"), ("8~12", "回"))

    def test_shared_file(self):
        text = self.write("all.txt", "post A 82%\fpost B 82% 82%\f")
        p = self.reg(row(document="A"), row(id="n2", document="B", page="2"), row(id="n3", document="B", page="2"))
        code, out = self.run_main(p, "--text", f"A={text}", "--text", f"B={text}")
        self.assertEqual(code, 0, out)
        self.assertIn("(texts: 1 files, 2 documents)", out)
        p = self.reg(row(document="A"), row(id="n2", document="B", page="2"))
        code, out = self.run_main(p, "--text", f"A={text}", "--text", f"B={text}")
        self.assertIn("MISSED\tA+B p.2: 82% occurs 2 times, register has 1", out)

    def test_page_past_end(self):
        text = self.write("a.txt", "82%\f")
        code, out = self.run_main(self.reg(row(page="3")), "--text", f"A={text}")
        self.assertEqual(code, 1)
        self.assertIn("past the end", out)

    def test_bad_input(self):
        cases = [
            "id\tvalue\nx\t1\n",
            HEADER + "\n",
            HEADER + "\n" + row() + "\textra\n",
            HEADER + "\tid\n" + row() + "\tx\n",
            HEADER + "\n" + row(value="about 82%") + "\n",
            HEADER + "\n" + row(page="p1") + "\n",
            HEADER + "\n" + row(placeholder="maybe") + "\n",
            HEADER + "\n" + row() + "\n" + row() + "\n",
            HEADER + "\n" + row(measures="") + "\n",
            HEADER + "\n" + row(note="x" * 200000) + "\n",
        ]
        for c in cases:
            code, _ = self.run_main(self.write("b.tsv", c))
            self.assertEqual(code, 2, c[:80])
        p = self.reg(row())
        for args in (["--text", "A"], ["--text", "A=/nonexistent"], ["--text", f"A={p}", "--text", f"A={p}"],
                     ["--text", "=x"]):
            code, _ = self.run_main(p, *args)
            self.assertEqual(code, 2, args)

    def test_bom_and_crlf(self):
        p = self.write("c.tsv", HEADER + "\r\n" + row() + "\r\n", encoding="utf-8-sig")
        code, out = self.run_main(p)
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
