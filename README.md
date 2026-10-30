# phm-case-kit

Reproducible kit for the blog series **"From One Line to Every Site, in Japan and Overseas: Company-wide DX and Predictive Maintenance at a Hypothetical Large Japanese Manufacturer"** (Hypothetical Technical Blog, from Blog #37).

The kit holds the tools used to check quotes, figures and dated facts in hypothetical case documents against **public sources only**.

日本語版: [README.ja.md](README.ja.md)

## Status

Version 1.7, in preparation (version 1.6 released on 30 October 2026, version 1.5 the same day, version 1.4 on 29 October 2026, versions 1.3, 1.2 and 1.1 the same day, version 1.0 on 28 October 2026). Tools are added together with the posts that use them. Standard library only; Python 3.9 or later.

| Tool | What it does | Post |
| --- | --- | --- |
| `tools/quotecheck.py` | Checks that each quotation is on the page given for it, flags how much an OK is worth, and runs a self-test that alters the quotations | Blog #37 |
| `tools/termcount.py` | Counts where a term occurs, page by page; a count of 0 is reported only as "not in the extracted text of these pages" | Blog #37 |
| `tools/sourcecheck.py` | Checks a source register, which traces each real-world fact in a document to a primary source, a secondary source or nowhere, and counts the rows by class | Blog #38 |
| `tools/numcheck.py` | Checks a number register: where one value carries more than one definition across related documents, and whether the register missed an occurrence | Blog #39 |
| `tools/datecheck.py` | Checks a register of dated facts: whether each was true on the document's date and is true now, whether a later event is being called an error, and which rows are due to be checked again | Blog #40 |
| `tools/calccheck.py` | Recalculates a register of numbers taken from a document: whether each total or product gives the number shown, and whether any recorded reading reproduces a number whose calculation the document does not give | Blog #41 |
| `tools/quotediff.py` | For a quotation that is not word for word, finds the passage in the source it most resembles and lists what was left out, added or replaced | Blog #42 |
| `tools/briefcheck.py` | Checks that every number and quotation in a one-page brief cites a source, that fictional figures are marked as fictional, and that every source has a date | Blog #43 |
| `tools/glosscheck.py` | Counts, in English versions of Japanese posts, the renderings a glossary says to avoid, the variants of a fixed rendering, and the Japanese terms whose rendering is missing | Blog #44 |

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

**sourcecheck** checks a register, not the facts: it cannot open a source. The register is a tab-separated file with one row per fact and the columns `id`, `document`, `page`, `statement`, `cited_ref`, `source_kind` (`primary`, `secondary` or `none`), `source_title`, `issuer`, `edition`, `url`, `location`, `underlying` (the statistic the source itself rests on), `accessed` (YYYY-MM-DD), `class` and `note`.

    python3 -I tools/sourcecheck.py register/sources_hcs17.tsv --as-of 2026-10-29

Classes: `A` the primary source says it as the document wrote it; `B` the primary source says it, but a qualifier, premise, year, scope or unit was dropped or changed; `C` found only in a secondary source; `D` the primary source says something different; `E` could not be checked. The checks: required fields, with a note for B to E (R1); allowed values (R2); A, B and D need a primary source with a title and a location (R3); C needs the secondary source (R4); a URL needs an accessed date, and any accessed date must be written YYYY-MM-DD and be no later than `--as-of` (R5); duplicate ids (R6); E has no source: `source_kind` none and no title, URL or location (R7). A header that names a column twice, or a field too large to read, is bad input. `--quiet` prints only the summary. Exit status: 0 if no check fires, 1 if any does, 2 on bad input. Where a fact falls between two classes is a judgement, which the note should give. `register/sources_hcs17.tsv` traces the 14 real-world facts in Hypothetical Case Study #17 (a fictional document); its run is in `evidence/`.

**numcheck** checks a number register: one row per occurrence of a number in a set of related documents, with what that document says the number measures. The columns are `id`, `value` (as written, e.g. `82%`, `1.5年`, `8~12回`; full-width digits are read as half-width and a range is read with `~`), `document`, `page`, `quote` (a short quote containing the value, or empty), `measures`, `unit`, `base` (what it is a share of), `period`, `placeholder` (`yes` if marked like `[82]`) and `note`.

    python3 -I tools/numcheck.py register/numbers_hcs17.tsv --text '#17=hcs17.txt' --text '#17.25=hcs17_02.txt'

It reports `DRIFT` (one value, more than one definition: `measures`, `unit` or `base` differ) and `CONFLICT` (one definition, more than one value). These are findings to judge, not errors; `--strict` makes them exit 1. With `--text DOC=PATH` (repeatable; several documents compiled in one file may share it), it also checks that each quote is on its page and contains its value (`QUOTE`), and that each page holds as many occurrences of each value as the register has rows for it: more is `MISSED`, fewer is `EXTRA`. It searches every text for every value in the register, reading full-width digits and signs as half-width, allowing brackets and spaces (`[82] %`) and a range written with `~`, `〜`, `～` or a hyphen or dash (`[8-12]回` matches `8~12回`); a digit, comma, point or range sign just before does not count (`60-82%` is not `82%`), nor a digit just after (for a value with no suffix, nor a `%` or a decimal or thousands part). The text is counted with its whitespace, so numbers on two lines are not joined. Pass only documents you meant to inventory in full. `--header-lines` (default 0) and `--note-footer` drop lines as in quotecheck; `--quiet` prints only the summary. Exit status: 0 if no check fires, 1 if `QUOTE`, `MISSED` or `EXTRA` fires (or `DRIFT`/`CONFLICT` with `--strict`), 2 on bad input. `register/numbers_hcs17.tsv` records 75 occurrences of six values (80%, 82%, 1.5年, 3週間, 85%, 8~12回): 72 in Hypothetical Case Study #17 and the documents derived from it (all fictional, written by the author with generative AI) and 3 in Ohi's public series; rows for Ohi's public series, and for the card of it embedded in #17's preface, give only the page and what is measured, not his text. Its run is in `evidence/`.

**datecheck** checks a register of dated facts: facts that are true only as of a date. It keeps three dates apart: the document's date (`doc_date`, or `<=DATE` when only an upper bound is known), the date of the event that decides the fact (`event_date`: a year, a month or a day), and the date the source was opened (`accessed`), and it adds the date by which the row should be checked again (`recheck_by`). The other columns are `id`, `document`, `page`, `statement`, `event`, `status_then` and `status_now` (`true`, `false` or `unknown`), `source_title`, `url`, `class` and `note`.

    python3 -I tools/datecheck.py register/dated_hcs17.tsv --as-of 2026-10-29

Classes: `CURRENT` held on the document's date and holds now; `SUPERSEDED` holds as a record of its time, but what it cites has since been replaced by a newer edition or version (the replacement may come before the document, when an older edition is cited after a newer one is out); `STALE` held then, no longer holds; `WRONG-THEN` did not hold even then; `UNDATED` depends on a date the document does not give; `CANNOT` could not be checked. The checks: required fields, including `recheck_by`, a source title (except for CANNOT), an event date for SUPERSEDED, STALE and WRONG-THEN, and a note for every class but CURRENT (T1); allowed values and date forms (T2); class and statuses agree, and an UNDATED row may not be false then, or true then and false now (T3); hindsight: WRONG-THEN whose event comes after the document, STALE whose event comes before it, or STALE or SUPERSEDED whose event has not happened by `--as-of` (T4; an event dated by year or month is compared by its whole period); a URL needs an accessed date, and no accessed date may be later than `--as-of` (T5); duplicate ids (T6); a row whose `recheck_by` is on or before `--as-of` is due to be checked again (T7). Exit status: 0 if no check fires, 1 if any does, 2 on bad input. `register/dated_hcs17.tsv` records 21 rows on dated facts in Hypothetical Case Study #17 and the documents derived from it (all fictional, written by the author with generative AI). It is a selection from an inventory of about 27 items made for Blog #40: it keeps every item about Japan's rules, white papers and disclosure and about international standards and frameworks that could be checked against a primary source, and leaves out foreign laws, figures from international bodies and items that could not be fully checked. A fact used by several documents may have one row or several. Its run is in `evidence/`.

**calccheck** recalculates a register of numbers taken from a document. Each row is one number: `id`, `document`, `page`, `label`, `shown` (as the document shows it), `value` (a plain decimal in the register's unit, 82% as 0.82, or `-`), `places` (decimals shown), `kind`, `formula`, `of` and `note`. Kinds: `input` (given, not derived), `derived` (shown with the document's own formula), `candidate` (one reading of how a shown number might have been calculated, when the document does not say; `of` names that number) and `placeholder` (left open, such as `[X]`, or not given at all). Formulas use `+ - * /`, parentheses, decimal numbers and other rows' ids; they are parsed, not evaluated as Python, and the arithmetic is exact. A formula that names a derived row uses that row's calculated value; to use a shown value as it stands, record it as an input row. Rows are calculated in dependency order. Limits: formulas of at most 2,000 characters, values of at most 40 characters, places from 0 to 12, calculated values of at most 4,000 bits (about 1,200 digits). A row that only depends on a row whose value a register problem leaves unknown is not reported again, and a row with its own register problem is not checked for `MISMATCH`; a number whose candidates all fail on register problems gets no `NOREPRO`, and `NOREPRO` names any candidate that could not be calculated. `--quiet` prints only the summary.

    python3 -I tools/calccheck.py register/calc_hcs17_25.tsv

A calculated value matches when it lies within half a unit of the last shown place. Findings about the document: `MISMATCH` (a derived row does not give the number shown), `NOREPRO` (a shown number has candidates, none of which gives it) and `UNRESOLVED` (a formula needs a placeholder). Register problems: required fields and allowed values (R1), formulas that do not parse or name an unknown id (R2), a formula that refers back to its own row (R3), duplicate ids (R4), and `of` naming a row without a shown value (R5). R2 also covers a division by zero and a calculated value past the size limit, and R3 reports every row in a loop. The tool checks arithmetic, not meaning: it cannot tell a rate of hours from a rate of money. Exit status: 0 if nothing fires, 1 if a check or finding fires, 2 on bad input. `register/calc_hcs17_25.tsv` records the business-plan outline template Hypothetical Case Study #17.25 (fictional, written by the author with generative AI), with one value printed in a table of #17 (p. 7, an image); a few rows are readings the document does not state, and each says so in its note. Its run is in `evidence/`.

**quotediff** compares quotations with their source. Each row of the register is one quotation: `id`, `document`, `page`, `source` (a name given with `--text`), `quote` (without its quote marks; the tool removes whitespace and applies NFKC before comparing, so the register may record it that way), `marked` (`none`, `ellipsis` when the document shows omissions with `…`, `‥`, `⋯`, `...`, `．．．`, `・・・`, `･･･` or `／`, the parts being in order and each within 400 characters of the one before, trying every place where the first part occurs, `paraphrase` when it says it is a summary) and `note`.

    python3 -I tools/quotediff.py register/quotes_hcs17.tsv --text '#17=hcs17.txt' --note-footer

Both texts are compared without whitespace and after Unicode NFKC. Classes: `EXACT`, `ELLIPSIS` (every part between the marks is in the source, in order), `PARAPHRASE` (marked, and not exact), `ALTERED` (a passage with similarity of at least `--min-ratio`, default 0.6, exists; the tool lists omissions, additions and replacements, character by character, so a reordering shows as an omission and an addition) and `NOT-FOUND`. `ALTERED` and `NOT-FOUND` are findings (exit 1); register problems are Q1 (required fields, allowed values), Q2 (a source with no `--text`) and Q3 (duplicate ids); bad input exits 2. `register/quotes_hcs17.tsv` records 101 passages that Hypothetical Case Study #17's derived documents present as quotations of #17 (all fictional, written by the author with generative AI). It is the inventory made for Blog #42, not a complete list: a review found at least two more, and remarks of fictional personas are left out. Pages of #17.2–#17.20 are pages of a compiled file of those posts; the posts used in Blog #42 were also checked against the published articles. pdftotext moves a leading English word to another line in three of #17's paragraphs, so three rows that match on the page image show as `ALTERED`; their notes say so. Quotations attributed to Takeaki Ohi are not in the register. Its run is in `evidence/`.

**briefcheck** checks a one-page brief written in Markdown with a numbered list of sources under a heading named `出典` or `Sources`, cited in the text as `[1]`, `[2, 3]` or `［1］`. B1: a line with a number or a quotation cites no source (a date followed by 時点 or preceded by "as of" is not counted); B2: a citation names a source not in the list; B3: a source is never cited; B4: a line cites a source whose entry says 架空 or fictional but does not say so itself; B5: a source's entry has no date; B6: the checked lines are longer than `--max-chars` characters in all (default 1600; a rough guide to one page in Japanese, not a page count; raise it for an English brief). Headings below the title and every line outside the source entries are checked; the sources section ends at the first line that is neither an entry nor an indented continuation of one; a line indented under a list item, with no blank line between, is joined to it; a table row is a line, so cite the source on each row; a list item's own number is not counted, but numbers such as 第8回 are; sources may be auto-numbered (`1.` repeated) and wrapped onto indented lines. It checks the brief's form, not its facts. Exit status: 0 if nothing fires, 1 if anything does, 2 on bad input.

    python3 -I tools/briefcheck.py examples/brief_hcs17.ja.md

`templates/brief_template.ja.md` and `templates/brief_template.en.md` are blank briefs. `examples/brief_hcs17.ja.md` is the brief made in Blog #43 for the fictional Hypothetical Case Study #17, with Takeaki Ohi's two sentences replaced by placeholders, since the kit holds no third-party text; `examples/brief_draft.ja.md` is a weak draft made to show the checks firing. Their runs are in `evidence/`.

**glosscheck** checks English versions against a glossary (`register/glossary_series.tsv`: one row per Japanese term, with columns `id`, `ja`, `en` (the rendering to use; several accepted forms separated by ` | `), `variants` (renderings seen that differ from it), `avoid` (renderings never to use) and `note`). It reports `AVOID` (a rendering never to use appears), `VARIANT` (a variant appears) and, with `--pair JA=EN`, `MISSING` (the Japanese term is in the Japanese file, but neither its rendering nor a variant is in the English). English forms match as whole words, case-insensitively unless the form has a capital letter; a form ending in a letter also matches its plural in -s or -es, and a space or hyphen in a form matches any run of spaces, line breaks or hyphens. Text matched by the rendering to use is not reported, and of two overlapping variants only the longer is. Glossary problems: G1 a required field is empty, G2 a duplicate id, G3 a form listed twice in one row. It checks wording, not meaning: it cannot tell when one English word is used for two Japanese terms, or whether a rendering fits its sentence. A post that names a rendering in order to say it is not used is still reported; the reader decides. Exit status: 0 if nothing fires, 1 if anything does, 2 on bad input.

    python3 -I tools/glosscheck.py register/glossary_series.tsv --pair ja.md=en.md

The glossary was drafted from the translation checks of Hypothetical Technical Blog #37–#41. Its variants are renderings found in their published English versions; the rendering to use is the one the checks recommended, which for one term (DX投資促進税制) does not yet appear in them. The run on those five posts is in `evidence/`; the posts themselves are not in the kit.

## Tests

    python3 -m unittest discover -s tests

The tests use a synthetic source written for them.

## Tags

- `v1.0` → 88eb816, made by the author on GitHub on 28 October 2026 (13:58 JST). Not immutable: release immutability was turned on after it.

- `v1.1` → 299422f, made by the author on GitHub on 29 October 2026 (09:57 JST). Immutable.

- `v1.2` → c5c6ac3, made by the author on GitHub on 29 October 2026 (10:49 JST). Immutable.

- `v1.3` → 7df67ed, made by the author on GitHub on 29 October 2026 (11:35 JST). Immutable.

- `v1.4` → a4d438c, made by the author on GitHub on 30 October 2026 (10:38 JST). Immutable.

- `v1.5` → 5e2d3f4, made by the author on GitHub on 30 October 2026 (11:11 JST). Immutable.

The tag `v1.6` is made by the author on GitHub after the release commit; until it exists, this list does not include it.

## Posts that use the kit

- Hypothetical Technical Blog #37, *What This Zero Checked* (28 October 2026; English, 29 October): `quotecheck.py`, `termcount.py`. https://note.com/ayako_iuchi/n/ne55386ce1ffc
- Hypothetical Technical Blog #38, *Where Did That Number Come From?* (29 October 2026): `sourcecheck.py`, `register/sources_hcs17.tsv`. https://note.com/ayako_iuchi/n/nd17f26a59311
- Hypothetical Technical Blog #39, *What Does That 82% Measure?* (30 October 2026): `numcheck.py`, `register/numbers_hcs17.tsv`. https://note.com/ayako_iuchi/n/n4cb5a26625db
- Hypothetical Technical Blog #40, *True as of When?* (30 October 2026): `datecheck.py`, `register/dated_hcs17.tsv`. https://note.com/ayako_iuchi/n/n16c739264aab
- Hypothetical Technical Blog #41, *How Was That 1.5 Years Calculated?* (30 October 2026): `calccheck.py`, `register/calc_hcs17_25.tsv`. https://note.com/ayako_iuchi/n/n4489e7f4efd9
- Hypothetical Technical Blog #42, *Is That Quotation Word for Word?*: `quotediff.py`, `register/quotes_hcs17.tsv`
- Hypothetical Technical Blog #43, *Does That One Page Show Its Sources?*: `briefcheck.py`, `templates/`, `examples/`
- Hypothetical Technical Blog #44, *Is It the Same English Every Time?* (published after this release): `glosscheck.py`, `register/glossary_series.tsv`

## Ground rules

- **All cases are fictional.** The companies, people and figures in the case documents (Hypothetical Case Study #17 and its derivatives) were created by the author with generative AI. They are not records of any real company.
- **Public sources only.** The method behind the series is Takeaki Ohi's (CEO, Kompas Co. Ltd.) public note magazine on 予兆管理, which renders the term in English as "Predictive Maintenance / Prognostics and Health Management - PHM". Only what can be checked in that public source is attributed to him.
- **No third-party text in this repository.** Source PDFs and their text extracts are never committed. The tools read files you supply yourself.
- Not affiliated with or endorsed by any company mentioned.

## Licenses

- Code: MIT ([LICENSE](LICENSE))
- Documents and data written for this kit: CC BY 4.0 ([LICENSE-DOCS](LICENSE-DOCS))

This kit was written for learning purposes. Generative AI was used in writing it. The views expressed here are my own and do not represent the official views of the company I work for.
