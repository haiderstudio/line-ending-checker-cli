#!/usr/bin/env python3
"""Check files use one line ending style, fail CI on mixed or wrong endings.

Run: python3 src/line_ending_checker.py examples/clean.txt
     python3 src/line_ending_checker.py examples/mixed.txt
     python3 src/line_ending_checker.py examples/files/
     python3 src/line_ending_checker.py --style crlf examples/clean.txt

The problem is quiet: a file that mixes LF and CRLF line endings
makes diffs noisy — every line looks changed when the ending flips —
and it breaks scripts that expect one style. A team on mixed
Windows, Mac, and Linux hits this constantly, and nobody notices
until a pull request is full of phantom changes. This tool reads
each file, reports every line whose ending is not the style you
asked for (LF by default), with its file and line number, and
exits 1 when any problem is found, so it can fail a CI run. A
clean file exits 0.

A file that is pure CRLF is reported line by line, not as one
vague file-level warning — you see exactly which lines need
fixing. A lone CR ending (old Mac style) is reported too. An
empty file passes: it has no endings to get wrong. A file whose
last line has no terminator is not a problem — this tool checks
endings, not the final newline. A binary file (a null byte in the
first 8 KB) is skipped and named on standard error, not failed
and not counted.

It never rewrites a file. It is report-only and runs fully offline:
it sends nothing anywhere and needs no API key.

Exit codes: 0 when every checked file uses the expected style,
1 when any line ending is wrong, 2 for a usage or input problem
(a missing path, a bad flag, no files to check).

Python standard library only.
"""

import argparse
import fnmatch
import json
import os
import sys
from pathlib import Path

VERSION = "1.0.0"

BINARY_PROBE = 8192


def scan_bytes(data):
    """Return a list of (line number, ending) for each line in data.

    ending is "LF", "CRLF", "CR", or None for a last line with no
    terminator. An empty file returns an empty list.
    """
    lines = []
    line_no = 1
    i = 0
    n = len(data)
    while i < n:
        byte = data[i]
        if byte == 0x0A:
            if i > 0 and data[i - 1] == 0x0D:
                lines.append((line_no, "CRLF"))
            else:
                lines.append((line_no, "LF"))
            line_no += 1
            i += 1
        elif byte == 0x0D:
            if i + 1 < n and data[i + 1] == 0x0A:
                i += 1
            else:
                lines.append((line_no, "CR"))
                line_no += 1
                i += 1
        else:
            i += 1
    if n > 0 and data[-1] not in (0x0A, 0x0D):
        lines.append((line_no, None))
    return lines


def check_bytes(data, expected="LF"):
    """Return the problems in one file's bytes, as a list of dicts.

    Each problem has `line` and `found` (the ending on that line).
    `expected` is "LF" or "CRLF". A line with no terminator is
    never a problem.
    """
    problems = []
    for line_no, ending in scan_bytes(data):
        if ending is None:
            continue
        if ending != expected:
            problems.append({"line": line_no, "found": ending})
    return problems


def is_binary(data):
    """True when the data looks binary: a null byte early on."""
    return b"\x00" in data[:BINARY_PROBE]


def collect_from_file(path, expected):
    """Return (problems, skipped) for one file.

    problems is a list of dicts; skipped is True when the file is
    binary and was not checked.
    """
    try:
        data = path.read_bytes()
    except OSError as exc:
        return (
            [
                {
                    "line": 0,
                    "found": "",
                    "error": f"cannot read file: {exc.strerror}",
                }
            ],
            False,
        )
    if is_binary(data):
        return [], True
    return [
        {"line": p["line"], "found": p["found"], "error": ""}
        for p in check_bytes(data, expected)
    ], False


def gather(paths, exclude, recursive, expected):
    """Walk the given paths and return (entries, checked, skipped).

    entries is a list of (file, problem); checked is a list of
    every text file read, clean or not; skipped is a list of
    binary files named but not checked. A file passed on the
    command line is always checked, even if it matches --exclude.
    """
    entries = []
    checked = []
    skipped = []
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            raise FileNotFoundError(raw)
        if path.is_file():
            problems, was_skipped = collect_from_file(path, expected)
            if was_skipped:
                skipped.append(str(path))
            else:
                checked.append(str(path))
            for problem in problems:
                entries.append((str(path), problem))
            continue
        if recursive:
            for dirpath, dirnames, filenames in _walk(path):
                for name in filenames:
                    candidate = Path(dirpath) / name
                    if _excluded(candidate, path, exclude):
                        continue
                    problems, was_skipped = collect_from_file(
                        candidate, expected
                    )
                    if was_skipped:
                        skipped.append(str(candidate))
                    else:
                        checked.append(str(candidate))
                    for problem in problems:
                        entries.append((str(candidate), problem))
        else:
            for candidate in sorted(path.iterdir()):
                if not candidate.is_file():
                    continue
                if _excluded(candidate, path, exclude):
                    continue
                problems, was_skipped = collect_from_file(
                    candidate, expected
                )
                if was_skipped:
                    skipped.append(str(candidate))
                else:
                    checked.append(str(candidate))
                for problem in problems:
                    entries.append((str(candidate), problem))
    return entries, checked, skipped


def _walk(root):
    """os.walk that never enters .git and never follows links."""
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        yield dirpath, dirnames, sorted(filenames)


def _excluded(candidate, root, patterns):
    name = candidate.name
    try:
        rel = str(candidate.relative_to(root))
    except ValueError:
        rel = name
    return any(
        fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel, pattern)
        for pattern in patterns
    )


def _format_problem(location, problem, expected):
    if problem["error"]:
        if problem["line"]:
            return f"FAIL {location}:{problem['line']}: {problem['error']}"
        return f"FAIL {location}: {problem['error']}"
    return (
        f"FAIL {location}:{problem['line']}: "
        f"{problem['found']} line ending (expected {expected})"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="line-ending-checker-cli",
        description="Check files use one line ending style.",
    )
    parser.add_argument("paths", nargs="*", help="files or folders to check")
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="read one document from standard input",
    )
    parser.add_argument(
        "--style",
        choices=["lf", "crlf"],
        default="lf",
        help="the line ending style to expect (default: lf)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="skip files matching this glob (repeatable)",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="do not walk into subfolders",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the result as JSON (summary goes to stderr)",
    )
    parser.add_argument("--version", action="store_true", help="print the version")
    args = parser.parse_args(argv)

    if args.version:
        print(f"line-ending-checker-cli {VERSION}")
        return 0

    expected = args.style.upper()

    entries = []
    checked_files = set()
    skipped_files = []
    try:
        if args.paths:
            found, checked, skipped = gather(
                args.paths, args.exclude, not args.no_recursive, expected
            )
            entries.extend(found)
            checked_files.update(checked)
            skipped_files.extend(skipped)
    except FileNotFoundError as exc:
        print(f"error: no such file or folder: {exc}", file=sys.stderr)
        return 2

    if args.stdin:
        data = sys.stdin.buffer.read()
        if is_binary(data):
            skipped_files.append("<stdin>")
        else:
            for problem in check_bytes(data, expected):
                entries.append(
                    (
                        "<stdin>",
                        {
                            "line": problem["line"],
                            "found": problem["found"],
                            "error": "",
                        },
                    )
                )
            checked_files.add("<stdin>")

    for name in skipped_files:
        print(f"SKIP {name}: binary file, not checked", file=sys.stderr)

    if not checked_files:
        print("error: no text files to check", file=sys.stderr)
        return 2

    problems = entries
    bad_files = len({f for f, _p in problems})
    total = len(problems)

    if args.json:
        files = []
        for name in sorted(checked_files):
            file_problems = [p for f, p in problems if f == name]
            files.append({"file": name, "problems": file_problems})
        result = {
            "files": files,
            "summary": {
                "checked": len(checked_files),
                "files_with_problems": bad_files,
                "problems": total,
                "skipped": len(skipped_files),
                "expected": expected,
            },
        }
        print(json.dumps(result, indent=2))
        if problems:
            print(
                f"Checked {len(checked_files)} file(s), {total} "
                f"problem(s) in {bad_files} file(s).",
                file=sys.stderr,
            )
        else:
            print(
                f"OK — {len(checked_files)} file(s) checked, "
                f"all line endings are {expected}.",
                file=sys.stderr,
            )
        return 1 if problems else 0

    for location, problem in problems:
        print(_format_problem(location, problem, expected))
    if problems:
        print(
            f"Checked {len(checked_files)} file(s), {total} "
            f"problem(s) in {bad_files} file(s)."
        )
        return 1
    print(
        f"OK — {len(checked_files)} file(s) checked, "
        f"all line endings are {expected}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
