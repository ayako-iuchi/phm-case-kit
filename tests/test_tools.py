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
        self.assertEqual(self.res["3"]["found"], ["2"])
        self.assertEqual(self.res["4"]["verdict"], "MISSING")
        self.assertEqual(self.res["7"]["verdict"], "OK")

    def test_flags(self):
        self.assertIn("SHORT", self.res["5"]["flags"])
        self.assertIn("MULTI", self.res["5"]["flags"])
        self.assertIn("LINE", self.res["5"]["flags"])
        self.assertEqual(self.res["5"]["found"], ["1", "2"])
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
        self.assertEqual(skipped, {"not_ok": 0, "short": 0})
        self.assertEqual(stats["replace_middle"]["caught"], 3)
        self.assertEqual(stats["delete_middle"]["caught"], 3)
        # a shortened quotation is still on the page: never caught
        self.assertEqual(stats["drop_first"]["caught"], 0)
        self.assertEqual(stats["drop_last"]["caught"], 0)

    def test_short_quotes_skipped_by_mutation(self):
        rows = [{"id": "x", "a": 2, "b": 2, "quote": "本文"}]
        stats, skipped = quotecheck.mutate(self.texts, rows)
        self.assertEqual(skipped, {"not_ok": 0, "short": 1})
        self.assertEqual(stats["replace_middle"]["tried"], 0)

    def test_mutation_leaves_out_rows_that_are_not_ok(self):
        # all seven rows: 3 (ELSEWHERE) and 4 (MISSING) must not count as caught
        stats, skipped = quotecheck.mutate(self.texts, self.rows)
        self.assertEqual(skipped, {"not_ok": 2, "short": 0})
        self.assertEqual(stats["drop_first"], {"tried": 5, "caught": 0, "elsewhere": 0})
        self.assertEqual(stats["drop_last"]["caught"], 0)

    def test_mutate_through_main_with_failing_rows(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            quotecheck.main([self.src, self.q, "--note-footer", "--mutate", "--quiet"])
        out = buf.getvalue()
        self.assertIn("left out: 2 not OK, 0 under 4 characters", out)
        self.assertIn("drop_first: caught 0 of 5", out)

    def test_minimum_length_for_mutation_is_four(self):
        rows = [{"id": "a", "a": 2, "b": 2, "quote": "本文で"}, {"id": "b", "a": 2, "b": 2, "quote": "本文です"}]
        stats, skipped = quotecheck.mutate(self.texts, rows)
        self.assertEqual(skipped["short"], 1)
        self.assertEqual(stats["replace_middle"]["tried"], 1)

    def test_middle_change_is_not_always_caught(self):
        p = write(self.tmp, "a.txt", "h\naaaaa\n\f")
        t = pages.page_texts(pages.read_pages(p))
        stats, _ = quotecheck.mutate(t, [{"id": "x", "a": 1, "b": 1, "quote": "aaaa"}])
        self.assertEqual(stats["delete_middle"]["caught"], 0)

    def test_short_boundary_and_median(self):
        rows = [{"id": "1", "a": 1, "b": 1, "quote": "あいうえおかきくけこ"},
                {"id": "2", "a": 1, "b": 1, "quote": "あいうえおかきくけこさ"}]
        p = write(self.tmp, "k.txt", "h\nあいうえおかきくけこさ\n\f")
        ps = pages.read_pages(p)
        res = quotecheck.check(pages.page_texts(ps), [set()], rows)
        self.assertIn("SHORT", res[0]["flags"])      # 10 characters
        self.assertNotIn("SHORT", res[1]["flags"])   # 11 characters
        self.assertEqual(quotecheck.summarize(res)["median_len"], 10.5)

    def test_quote_across_a_page_break(self):
        p = write(self.tmp, "b.txt", "h\none two three\n\fh\nfour five\n\f")
        ps = pages.read_pages(p)
        t, ls = pages.page_texts(ps), [set() for _ in ps]
        rows = [{"id": "1", "a": 1, "b": 1, "quote": "three four"},
                {"id": "2", "a": 1, "b": 2, "quote": "three four"}]
        res = quotecheck.check(t, ls, rows)
        self.assertEqual((res[0]["verdict"], res[0]["found"]), ("ELSEWHERE", ["1-2"]))
        self.assertEqual((res[1]["verdict"], res[1]["found"]), ("OK", ["1-2"]))

    def test_double_quotes_are_ordinary_characters(self):
        src = write(self.tmp, "dq.txt", 'h\ngamma "delta" eps\n\f')
        q = write(self.tmp, "dq.tsv",
                  'id\tpage_from\tpage_to\tquote\tnote\n'
                  '1\t1\t1\t"delta" eps\t"see also\n'
                  '2\t1\t1\tnot in the source\t\n'
                  '3\t1\t1\talso absent\tx"\n')
        rows = quotecheck.load_quotes(q)
        self.assertEqual([r["quote"] for r in rows], ['"delta" eps', "not in the source", "also absent"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(quotecheck.main([src, q, "--quiet"]), 1)
        self.assertIn("OK: 1  ELSEWHERE: 0  MISSING: 2", buf.getvalue())

    def test_byte_order_mark(self):
        q = os.path.join(self.tmp, "bom.tsv")
        with open(q, "w", encoding="utf-8-sig") as f:
            f.write("id\tpage_from\tpage_to\tquote\n1\t1\t1\t（第2回）\n")
        self.assertEqual(len(quotecheck.load_quotes(q)), 1)

    def test_footer_and_own_regex_together(self):
        ps = pages.read_pages(self.src, drop_line_regex=["(?i)^最終回", quotecheck.NOTE_FOOTER])
        flat = [ln for p in ps for ln in p]
        self.assertFalse(any("note.com" in ln or ln.startswith("最終回") for ln in flat))

    def test_evidence_columns(self):
        out = os.path.join(self.tmp, "ev2.tsv")
        with redirect_stdout(io.StringIO()):
            quotecheck.main([self.src, self.q, "--note-footer", "--evidence", out])
        with open(out, encoding="utf-8") as f:
            rows = [ln.rstrip("\n").split("\t") for ln in f][1:]
        by_id = {r[0]: r for r in rows}
        self.assertEqual(by_id["3"][4:], ["ELSEWHERE", "SHORT,DUP", "2"])  # 9 characters, same as row 2
        self.assertEqual(by_id["5"][5:], ["SHORT,MULTI,LINE", "1,2"])
        self.assertEqual(by_id["4"][3], "14")

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
                     "id\tpage_from\tpage_to\tquote\n1\t1\t9\tx\n",
                     "id\tpage_from\tpage_to\tquote\n"):
            q = write(self.tmp, "bad.tsv", text)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(quotecheck.main([self.src, q]), 2, text)


class ExitCodeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = write(self.tmp, "src.txt", SOURCE)
        self.q = write(self.tmp, "q.tsv", "id\tpage_from\tpage_to\tquote\n1\t1\t1\t（第2回）\n")

    def run_main(self, args):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return quotecheck.main(args)

    def test_bad_regex_is_exit_2(self):
        self.assertEqual(self.run_main([self.src, self.q, "--drop-line-regex", "("]), 2)

    def test_inline_flag_with_note_footer(self):
        self.assertEqual(self.run_main([self.src, self.q, "--drop-line-regex", "(?i)foot", "--note-footer"]), 0)

    def test_unwritable_evidence_is_exit_2(self):
        bad = os.path.join(self.tmp, "no", "such", "dir", "ev.tsv")
        self.assertEqual(self.run_main([self.src, self.q, "--evidence", bad]), 2)


class RoundTwoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_tab_inside_a_quotation_is_rejected(self):
        src = write(self.tmp, "s.txt", "h\none two\n\f")
        q = write(self.tmp, "t.tsv", "id\tpage_from\tpage_to\tquote\n1\t1\t1\tone two\tNOT THERE\n")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(quotecheck.main([src, q]), 2)

    def test_blank_lines_are_skipped(self):
        q = write(self.tmp, "b.tsv", "id\tpage_from\tpage_to\tquote\n1\t1\t1\tx\n\n")
        self.assertEqual(len(quotecheck.load_quotes(q)), 1)

    def test_page_break_found_beside_a_single_page(self):
        p = write(self.tmp, "p.txt", "h\none two\n\fh\nthree\n\fh\nx\n\fh\ntwo three\n\f")
        t = pages.page_texts(pages.read_pages(p))
        rows = [{"id": "1", "a": 1, "b": 1, "quote": "two three"}]
        res = quotecheck.check(t, [set() for _ in t], rows)
        self.assertEqual(res[0]["verdict"], "ELSEWHERE")
        self.assertEqual(res[0]["found"], ["4", "1-2"])
        self.assertIn("MULTI", res[0]["flags"])

    def test_note_footer_and_regex_through_main(self):
        src = write(self.tmp, "f.txt", "h\nkeep this\nDROP me\nhttps://note.com/x/n/n1 1/1\n\f")
        ok = write(self.tmp, "ok.tsv", "id\tpage_from\tpage_to\tquote\n1\t1\t1\tkeep this\n")
        gone = write(self.tmp, "g.tsv", "id\tpage_from\tpage_to\tquote\n1\t1\t1\tDROP me\n2\t1\t1\tnote.com\n")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(quotecheck.main([src, ok, "--note-footer", "--drop-line-regex", "(?i)^drop"]), 0)
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(io.StringIO()):
            self.assertEqual(quotecheck.main([src, gone, "--note-footer", "--drop-line-regex", "(?i)^drop", "--quiet"]), 1)
        self.assertIn("MISSING: 2", buf.getvalue())

    def test_source_with_byte_order_mark(self):
        p = os.path.join(self.tmp, "bom.txt")
        with open(p, "w", encoding="utf-8-sig") as f:
            f.write("header\nbody\n\f")
        self.assertEqual(pages.read_pages(p), [["body"]])


class PagesMoreTest(unittest.TestCase):
    def test_nbsp_and_en_dash_range(self):
        self.assertEqual(pages.norm("a\u00a0b"), "ab")
        self.assertEqual(pages.parse_range("2–4", 5), (2, 4))


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
