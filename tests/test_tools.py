"""Tests for quotecheck.py, termcount.py and pages.py.

The source text here is synthetic, written for these tests. No third-party
text is used. Run: python3 -m unittest discover -s tests
"""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

import pages  # noqa: E402
import quotecheck  # noqa: E402
import termcount  # noqa: E402

# Three pages. Each starts with a printed header line; pages 1 and 2 end with
# a note-style footer. Page 2 breaks a sentence and an English term across lines.
SOURCE = (
    "2026/10/28 9:00  Example magazine | header\n"
    "架空の連載　第一回\n"
    "設備の状態を見て、必要なときに\n"
    "  手入れをする考え方です。\n"
    "（第2回）\n"
    "https://note.com/example/n/n0000000000a1   1/3\n"
    "\f"
    "2026/10/28 9:00  Example magazine | header\n"
    "第二回の本文です。Condition\n"
    "Monitoring という語を使います。\n"
    "（第2回）\n"
    "https://note.com/example/n/n0000000000a2   2/3\n"
    "\f"
    "\n"
    "2026/10/28 9:01  Example magazine | header\n"
    "最終回です。ありがとうございました。\n"
    "\f"
)

QUOTES = (
    "id\tpage_from\tpage_to\tquote\tnote\n"
    "1\t1\t1\t設備の状態を見て、必要なときに手入れをする考え方です。\tbroken across lines\n"
    "2\t2\t2\t第二回の本文です。\tshort-ish\n"
    "3\t1\t1\t第二回の本文です。\twrong page\n"
    "4\t3\t3\tこの文はどこにもありません。\tmissing\n"
    "5\t2\t2\t（第2回）\tshort, on two pages, a whole line\n"
    "6\t1\t1\t設備の状態を見て、必要なときに手入れをする考え方です。\tduplicate of 1\n"
    "7\t2\t3\t最終回です。\trange\n"
)


def write(tmp, name, text):
    p = os.path.join(tmp, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


class PagesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = write(self.tmp, "src.txt", SOURCE)

    def test_split_and_header(self):
        ps = pages.read_pages(self.src)
        self.assertEqual(len(ps), 3)  # trailing empty page dropped
        self.assertFalse(any("header" in ln for p in ps for ln in p))

    def test_leading_blank_line_does_not_count_as_header(self):
        ps = pages.read_pages(self.src)
        self.assertEqual(ps[2][0], "最終回です。ありがとうございました。")

    def test_footer_regex(self):
        ps = pages.read_pages(self.src, drop_line_regex=quotecheck.NOTE_FOOTER)
        self.assertFalse(any("note.com" in ln for p in ps for ln in p))
        kept = pages.read_pages(self.src)
        self.assertTrue(any("note.com" in ln for ln in kept[0]))

    def test_norm_removes_all_whitespace_only(self):
        self.assertEqual(pages.norm(" a\tb\nc　d "), "abcd")
        self.assertEqual(pages.norm("「Ａ」"), "「Ａ」")  # no width or bracket mapping

    def test_parse_range(self):
        self.assertEqual(pages.parse_range(None, 5), (1, 5))
        self.assertEqual(pages.parse_range("2-4", 5), (2, 4))
        self.assertEqual(pages.parse_range("3", 5), (3, 3))
        for bad in ("0-2", "4-2", "1-6", "x"):
            with self.assertRaises(ValueError):
                pages.parse_range(bad, 5)


class QuotecheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = write(self.tmp, "src.txt", SOURCE)
        self.q = write(self.tmp, "q.tsv", QUOTES)
        ps = pages.read_pages(self.src, drop_line_regex=quotecheck.NOTE_FOOTER)
        self.texts = pages.page_texts(ps)
        self.lines = [set(pages.norm(ln) for ln in p if pages.norm(ln)) for p in ps]
        self.rows = quotecheck.load_quotes(self.q)
        self.res = {r["id"]: r for r in quotecheck.check(self.texts, self.lines, self.rows)}

    def test_verdicts(self):
        self.assertEqual(self.res["1"]["verdict"], "OK")
        self.assertEqual(self.res["3"]["verdict"], "ELSEWHERE")
        self.assertEqual(self.res["3"]["found"], [2])
        self.assertEqual(self.res["4"]["verdict"], "MISSING")
        self.assertEqual(self.res["7"]["verdict"], "OK")

    def test_flags(self):
        self.assertIn("SHORT", self.res["5"]["flags"])
        self.assertIn("MULTI", self.res["5"]["flags"])
        self.assertIn("LINE", self.res["5"]["flags"])
        self.assertEqual(self.res["5"]["found"], [1, 2])
        self.assertIn("DUP", self.res["6"]["flags"])
        self.assertNotIn("DUP", self.res["1"]["flags"])
        self.assertNotIn("LINE", self.res["1"]["flags"])  # spans two lines

    def test_summary(self):
        s = quotecheck.summarize(list(self.res.values()))
        self.assertEqual((s["rows"], s["distinct"]), (7, 5))  # rows 6 and 3 repeat rows 1 and 2
        self.assertEqual((s["OK"], s["ELSEWHERE"], s["MISSING"]), (5, 1, 1))

    def test_mutation_self_test(self):
        ok_rows = [r for r in self.rows if r["id"] in ("1", "2", "7")]
        stats, skipped = quotecheck.mutate(self.texts, ok_rows)
        self.assertEqual(skipped, 0)
        self.assertEqual(stats["replace_middle"]["caught"], 3)
        self.assertEqual(stats["delete_middle"]["caught"], 3)
        # a shortened quotation is still on the page: never caught
        self.assertEqual(stats["drop_first"]["caught"], 0)
        self.assertEqual(stats["drop_last"]["caught"], 0)

    def test_short_quotes_skipped_by_mutation(self):
        rows = [{"id": "x", "a": 2, "b": 2, "quote": "本文"}]
        stats, skipped = quotecheck.mutate(self.texts, rows)
        self.assertEqual(skipped, 1)
        self.assertEqual(stats["replace_middle"]["tried"], 0)

    def test_evidence_has_no_quotation_text(self):
        out = os.path.join(self.tmp, "ev.tsv")
        with redirect_stdout(io.StringIO()):
            code = quotecheck.main([self.src, self.q, "--note-footer", "--evidence", out])
        self.assertEqual(code, 1)  # rows 3 and 4 fail
        with open(out, encoding="utf-8") as f:
            ev = f.read()
        self.assertNotIn("設備", ev)
        self.assertNotIn("本文", ev)
        self.assertTrue(ev.startswith("id\tpage_from\tpage_to\tlength\tverdict\tflags\tfound_on_pages\n"))

    def test_exit_zero_when_all_ok(self):
        q = write(self.tmp, "ok.tsv", "id\tpage_from\tpage_to\tquote\n1\t1\t1\t（第2回）\n")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(quotecheck.main([self.src, q, "--quiet"]), 0)

    def test_bad_input(self):
        for text in ("id\tpage\tquote\n1\t1\tx\n",
                     "id\tpage_from\tpage_to\tquote\n1\t2\t1\tx\n",
                     "id\tpage_from\tpage_to\tquote\n1\ta\t1\tx\n",
                     "id\tpage_from\tpage_to\tquote\n1\t1\t1\t \n",
                     "id\tpage_from\tpage_to\tquote\n1\t1\t9\tx\n"):
            q = write(self.tmp, "bad.tsv", text)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(quotecheck.main([self.src, q]), 2, text)


class TermcountTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = write(self.tmp, "src.txt", SOURCE)
        self.texts = pages.page_texts(pages.read_pages(self.src))

    def test_term_across_line_break(self):
        self.assertEqual(termcount.count(self.texts, "Condition Monitoring", 1, 3), {2: 1})

    def test_absent_term_and_range(self):
        self.assertEqual(termcount.count(self.texts, "Predictive Management", 1, 3), {})
        self.assertEqual(termcount.count(self.texts, "（第2回）", 1, 1), {1: 1})
        self.assertEqual(termcount.count(self.texts, "（第2回）", 1, 3), {1: 1, 2: 1})

    def test_case(self):
        self.assertEqual(termcount.count(self.texts, "condition monitoring", 1, 3), {})
        self.assertEqual(termcount.count(self.texts, "condition monitoring", 1, 3, ignore_case=True), {2: 1})

    def test_overlapping_occurrences_counted(self):
        p = write(self.tmp, "o.txt", "h\naaaa\n\f")
        t = pages.page_texts(pages.read_pages(p))
        self.assertEqual(termcount.count(t, "aa", 1, 1), {1: 3})

    def test_main_output(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = termcount.main([self.src, "Predictive Management", "--pages", "1-2"])
        self.assertEqual(code, 0)
        self.assertIn("not in the extracted text of these pages", buf.getvalue())

        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(termcount.main([self.src, "x", "--pages", "1-9"]), 2)


if __name__ == "__main__":
    unittest.main()
