# Changelog

Revisions are dated and kept visible. Nothing is changed silently.

## Kit v1.0 — 2026-10-28

- First release of tools. Added `tools/pages.py`, `tools/quotecheck.py`, `tools/termcount.py`, `tests/test_tools.py`, `evidence/quotecheck_inventory_2026-10-28.txt`, `evidence/quotecheck_inventory_2026-10-28.tsv`, `CHANGELOG.md` and `CITATION.cff`. Standard library only.
- `quotecheck.py` generalizes the check the author ran on 28 October 2026 on an inventory of the source written by a separate agent: each quotation, with all whitespace removed, must be on the page given for it. It adds what that check did not report: duplicates, short quotations, quotations found on more than one page, quotations equal to a whole line, and a self-test that alters each quotation four ways. `termcount.py` counts where a term occurs, page by page.
- The evidence files record the run on the inventory's 350 quotation rows: 350 OK, 347 distinct, 44 of 10 characters or fewer, 15 on more than one page, 48 equal to a whole line; the self-test catches 349 of 349 replacements and deletions in the middle, and 0 of 349 shortenings at either end. They hold no quotation text. The earlier check dropped only lines starting with `https://note.com/kompas`; `--note-footer` drops lines starting with any note.com URL, and gives the same result on this source.
- Both READMEs describe the tools, what they do not check, the self-test, the tests and the evidence. The README's series line now says "from Blog #37": on 28 October 2026 the author decided that the technical posts of this theme continue the numbering of Hypothetical Technical Blog (the first is Blog #37), replacing the "PdM #1 / 予兆 #1" numbering in the initial commit.
- `CITATION.cff` names version 1.0 on this branch and has no `date-released`; the release commit writes the date on the day of the release.
