# phm-case-kit

Reproducible kit for the blog series **"From One Line to Every Site, in Japan and Overseas: Company-wide DX and Predictive Maintenance at a Hypothetical Large Japanese Manufacturer"** (Hypothetical Technical Blog, from Blog #37).

The kit holds the tools used to check quotes, figures and dated facts in hypothetical case documents against **public sources only**.

日本語版: [README.ja.md](README.ja.md)

## Status

Version 1.0 (unreleased on this branch). Tools are added together with the posts that use them. Standard library only; Python 3.9 or later.

| Tool | What it does | Post |
| --- | --- | --- |
| `tools/quotecheck.py` | Checks that each quotation is on the page given for it, flags how much an OK is worth, and runs a self-test that alters the quotations | Blog #37 |
| `tools/termcount.py` | Counts where a term occurs, page by page; a count of 0 is reported only as "not in the extracted text of these pages" | Blog #37 |

## Using the tools

You supply the source. Extract it yourself, keeping the page breaks:

    pdftotext -layout source.pdf source.txt

Write your quotations as a tab-separated file with the columns `id`, `page_from`, `page_to`, `quote` (a header row is required; other columns are ignored). Then:

    python3 -I tools/quotecheck.py source.txt quotes.tsv --note-footer --mutate --evidence results.tsv
    python3 -I tools/termcount.py source.txt "Predictive Management" "Predictive Maintenance" --pages 1-119 --note-footer

`--note-footer` drops lines that start with a note.com URL (the footer of a page printed from note, and also any body line that starts with such a link); `--header-lines` (default 1) drops that many lines from the top of every page, whatever they say. In the TSV, a double quotation mark is an ordinary character; a field cannot hold a tab or a line break, and a row with the wrong number of fields is rejected. Exit status: 0 if every row is OK, 1 if any is not, 2 on bad input.

**What quotecheck checks.** All whitespace is removed from the quotation and from the pages, and the quotation must be a substring of the given pages. A quotation that runs across a page break is found as such (reported as, say, `11-12`). Nothing else is normalized: 「」 and "", or full-width and half-width letters, stay different. A quotation is `OK`, `ELSEWHERE` (on other pages, which are listed) or `MISSING`. Flags say how much an OK is worth: `SHORT` (10 characters or fewer by default), `MULTI` (on more than one page), `DUP` (same text as an earlier row) and `LINE` (a whole line of the page, often a heading).

**What it does not check.** Whether a quotation is in context, is attributed to the right person, or supports the claim it is used for. It cannot tell an extraction defect from an error in the source, and it checks the PDF you saved, not the page as it is now.

**The self-test (`--mutate`).** For each quotation that is OK and has 4 characters or more, it makes four altered copies and counts how many the check would catch. Dropping the first or the last character is never caught, because a shortened quotation is still on the page: a quotation that was cut short passes this check. Whether a change in the middle is caught depends on the text, so the counts describe one run (on the inventory in `evidence/`, 349 of 349), not a guarantee.

**The evidence files** (`--evidence`) hold ids, pages, lengths, verdicts, flags and where each quotation occurs (`4` for a page, `1-2` for a page break it runs across), and no quotation text.

**termcount** removes whitespace before counting, so a term broken across lines is found; it counts overlapping occurrences, and not across a page break. A count of 0 means only that the term is not in the extracted text of those pages. `evidence/` holds the runs cited by the posts.

## Tests

    python3 -m unittest discover -s tests

The tests use a synthetic source written for them.

## Tags

None yet.

## Posts that use the kit

- Hypothetical Technical Blog #37 (in preparation): `quotecheck.py`, `termcount.py`

## Ground rules

- **All cases are fictional.** The companies, people and figures in the case documents (Hypothetical Case Study #17 and its derivatives) were created by the author with generative AI. They are not records of any real company.
- **Public sources only.** The method behind the series is Takeaki Ohi's (CEO, Kompas Co., Ltd.) public note magazine on 予兆管理, which renders the term in English as "Predictive Maintenance / Prognostics and Health Management - PHM". Only what can be checked in that public source is attributed to him.
- **No third-party text in this repository.** Source PDFs and their text extracts are never committed. The tools read files you supply yourself.
- Not affiliated with or endorsed by any company mentioned.

## Licenses

- Code: MIT ([LICENSE](LICENSE))
- Documents and data written for this kit: CC BY 4.0 ([LICENSE-DOCS](LICENSE-DOCS))

This kit was written for learning purposes. Generative AI was used in writing it. The views expressed here are my own and do not represent the official views of the company I work for.
