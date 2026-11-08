# line-ending-checker-cli

Check files use one line ending style, fail CI on mixed or wrong endings.

[![CI](https://github.com/haiderstudio/line-ending-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/line-ending-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`line_ending_checker` reads text files and checks every line
ending in them:

- A file that mixes LF and CRLF line endings makes diffs noisy
  — every line looks changed when the ending flips — and it
  breaks scripts that expect one style. A team on mixed
  Windows, Mac, and Linux hits this constantly, and nobody
  notices until a pull request is full of phantom changes. This
  tool reports every line whose ending is not the style you
  asked for (LF by default), with its file and line number, and
  exits 1 when any problem is found — so it can fail a CI run.
  A clean file exits 0.
- A file that is pure CRLF is reported line by line, not as one
  vague file-level warning — you see exactly which lines need
  fixing. A lone CR ending (old Mac style) is reported too.
- `--style crlf` checks for CRLF instead, for a Windows team
  that wants every file to end CRLF.
- An empty file passes: it has no endings to get wrong. A file
  whose last line has no terminator is not a problem — this
  tool checks endings, not the final newline.
- A binary file (a null byte in the first 8 KB) is skipped and
  named on standard error, not failed and not counted.
- Files come from the command line (one or more), or from a
  folder walk: every file under a folder, recursively by
  default (`--no-recursive` stops at the top level). `.git`
  folders are never walked, and directory links are never
  followed, so a link cycle cannot loop the check.
- `--exclude PATTERN` skips files by glob, for example
  `--exclude 'generated-*'`. It can be repeated. A file passed
  directly on the command line is always checked, even if it
  matches an exclude pattern.
- `--stdin` reads one document from standard input.
- `--json` prints the result as machine-readable JSON (the
  summary goes to standard error, so standard output stays
  clean JSON).
- It is report-only and runs fully offline: it never rewrites a
  file, sends nothing anywhere, and needs no API key.

## What it does NOT do

- It does not convert line endings or rewrite a file. A wrong
  ending is reported; fixing it is your job.
- It does not check trailing whitespace or the final newline —
  that is Day 42's `whitespace-checker-cli` job. This tool's
  one job is ending consistency.
- It does not check file encoding — a file that is not valid
  UTF-8 is still checked byte by byte for its endings.
- It does not fetch anything. Every input is a local file or
  standard input.

## Who it is for

Anyone who works on a team where Windows and Mac/Linux mix and
wants clean diffs: a developer keeping a repo tidy, or anyone
adding a CI step that fails the build when a file's endings
drift. A mixed file makes every line in a pull request look
changed — this catches it before the file is committed.

## How this differs from similar tools

The exact name `line-ending-checker-cli` matches 0
repositories on GitHub (checked Nov 8, 2026), and
`crlf checker cli` matches 0 too. The wider field is tiny:
`line ending checker` matches 2 repositories. The closest is
jvedder/LineEndingChecker, 1 star — a Java tool that checks
CRLF vs LF in a folder, with no test or CI claim. The other is
KalitaAlexey/missing_line_ending_checker, 0 stars, which
checks for a missing ending at the end of a file — a different
job. `eol checker` matches 23 repositories, all noise: tools
checking container-image end-of-life, Ubuntu versions from SSH
banners, or library end-of-life — none of them checks line
endings in files. None of them is a tested CLI that walks a
folder, reports every wrong ending with a file and line, and
exits 1 for CI. This tool does that one job: a Python
standard-library-only CLI that reads files, reports every line
whose ending is not the style you asked for, and exits 1 on a
wrong ending — no install beyond Python, no website, no
network.

## Install

Python standard library only — no packages to download. You need
Python 3.8 or newer. Clone the repo and run it in place:

```
git clone https://github.com/haiderstudio/line-ending-checker-cli.git
cd line-ending-checker-cli
python3 src/line_ending_checker.py examples/clean.txt
```

```
OK — 1 file(s) checked, all line endings are LF.
```

## Usage

Check one clean file:

```
python3 src/line_ending_checker.py examples/clean.txt
```

```
OK — 1 file(s) checked, all line endings are LF.
```

Check a file that is all CRLF:

```
python3 src/line_ending_checker.py examples/crlf.txt
```

```
FAIL examples/crlf.txt:1: CRLF line ending (expected LF)
FAIL examples/crlf.txt:2: CRLF line ending (expected LF)
FAIL examples/crlf.txt:3: CRLF line ending (expected LF)
Checked 1 file(s), 3 problem(s) in 1 file(s).
```

Check a mixed file — one CRLF line and one lone CR line:

```
python3 src/line_ending_checker.py examples/mixed.txt
```

```
FAIL examples/mixed.txt:2: CRLF line ending (expected LF)
FAIL examples/mixed.txt:4: CR line ending (expected LF)
Checked 1 file(s), 2 problem(s) in 1 file(s).
```

Check a whole folder:

```
python3 src/line_ending_checker.py examples/files/
```

```
FAIL examples/files/crlf.txt:1: CRLF line ending (expected LF)
FAIL examples/files/crlf.txt:2: CRLF line ending (expected LF)
FAIL examples/files/crlf.txt:3: CRLF line ending (expected LF)
FAIL examples/files/docs/notes.txt:2: CRLF line ending (expected LF)
Checked 4 file(s), 4 problem(s) in 2 file(s).
```

Check for CRLF style instead:

```
python3 src/line_ending_checker.py --style crlf examples/clean.txt
```

```
FAIL examples/clean.txt:1: LF line ending (expected CRLF)
FAIL examples/clean.txt:2: LF line ending (expected CRLF)
FAIL examples/clean.txt:3: LF line ending (expected CRLF)
FAIL examples/clean.txt:4: LF line ending (expected CRLF)
Checked 1 file(s), 4 problem(s) in 1 file(s).
```

Check one document from standard input:

```
printf 'a\nb\r\n' | python3 src/line_ending_checker.py --stdin
```

```
FAIL <stdin>:2: CRLF line ending (expected LF)
Checked 1 file(s), 1 problem(s) in 1 file(s).
```

Machine-readable output with `--json` (the summary goes to
standard error, so standard output stays clean JSON):

```
python3 src/line_ending_checker.py examples/mixed.txt --json
```

```
{
  "files": [
    {
      "file": "examples/mixed.txt",
      "problems": [
        {
          "line": 2,
          "found": "CRLF",
          "error": ""
        },
        {
          "line": 4,
          "found": "CR",
          "error": ""
        }
      ]
    }
  ],
  "summary": {
    "checked": 1,
    "files_with_problems": 1,
    "problems": 2,
    "skipped": 0,
    "expected": "LF"
  }
}
```

Exit codes: 0 when every checked file uses the expected style,
1 when any line ending is wrong, 2 for a usage problem (no
text files given, a bad flag, a missing file or folder).

## Examples

### 1. A pure CRLF file, line by line

`examples/crlf.txt` is three CRLF lines, and each one is
reported with its line number:

```
python3 src/line_ending_checker.py examples/crlf.txt
```

```
FAIL examples/crlf.txt:1: CRLF line ending (expected LF)
FAIL examples/crlf.txt:2: CRLF line ending (expected LF)
FAIL examples/crlf.txt:3: CRLF line ending (expected LF)
Checked 1 file(s), 3 problem(s) in 1 file(s).
```

### 2. A mixed file — CRLF and a lone CR in one file

`examples/mixed.txt` has five lines: line 2 ends CRLF, line 4
ends with a lone CR, the rest end LF:

```
python3 src/line_ending_checker.py examples/mixed.txt
```

```
FAIL examples/mixed.txt:2: CRLF line ending (expected LF)
FAIL examples/mixed.txt:4: CR line ending (expected LF)
Checked 1 file(s), 2 problem(s) in 1 file(s).
```

### 3. The bundled examples, all at once

```
sh examples/run-example.sh
```

The script checks the clean file (pass), then the CRLF file
(fail, on purpose), then the mixed file (fail, on purpose),
then the whole `examples/files/` folder (fail, on purpose —
it picks up `files/crlf.txt` and `files/docs/notes.txt`). Its
full output is in `examples/sample-output.md`, ending with
`Checked 4 file(s), 4 problem(s) in 2 file(s).` The failing
runs exit 1, which is the expected result — the script ends
with exit 0 so it can be run as a demo.

## How it is tested

58 tests, standard library `unittest` only, no packages to install:

```
python3 tests/test_line_ending_checker.py
```

The tests cover: line-ending scanning (pure LF, pure CRLF,
mixed, lone CR, CR/CRLF at end of file, empty file, no
trailing newline, blank lines), the style check (LF and CRLF
expected, every wrong line reported), binary detection (null
byte, plain text, empty, null past the 8 KB probe), file
collection (clean, CRLF, binary skipped, missing file), the
CLI (exit 0/1/2, `--style`, `--stdin`, `--json` output,
`--version`, bad flags, missing paths, empty folders, folder
walking, `--no-recursive`, `.git` skipped, `--exclude`,
several files at once, input files left unchanged, binary
files skipped), the bundled examples (sample output compared
byte-for-byte against a fresh run, and the README-quoted
outputs checked against it), and hygiene checks (no
placeholder text, no absolute paths, stdlib imports only,
`.env` first in `.gitignore`).

## Contributing

Small, focused improvements are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. The idea of
checking line endings is not new — the similar tools named
above (the 1-star Java folder checker, the 0-star missing-
ending checker) are listed in "How this differs" — but every
line of code here is original, and the tool builds on nothing
but Python's standard library.
