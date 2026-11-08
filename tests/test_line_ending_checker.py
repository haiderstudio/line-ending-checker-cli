#!/usr/bin/env python3
"""Tests for line-ending-checker-cli. Standard library unittest only.

Run from the repo root: python3 tests/test_line_ending_checker.py
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import line_ending_checker as lec  # noqa: E402

ALLOWED_STDLIB = {
    "argparse",
    "fnmatch",
    "json",
    "os",
    "sys",
    "pathlib",
}


def run_cli(argv, stdin_bytes=None):
    """Run main() in-process and capture (exit code, stdout, stderr)."""
    out = io.StringIO()
    err = io.StringIO()
    old_stdin = sys.stdin
    if stdin_bytes is not None:
        sys.stdin = _FakeStdin(stdin_bytes)
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = lec.main(argv)
    finally:
        sys.stdin = old_stdin
    return code, out.getvalue(), err.getvalue()


class _FakeStdin:
    """Minimal stdin with a .buffer, for --stdin tests."""

    def __init__(self, data):
        self.buffer = io.BytesIO(data)


def write_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


class ScanBytesTests(unittest.TestCase):
    def test_pure_lf(self):
        self.assertEqual(
            lec.scan_bytes(b"a\nb\nc\n"),
            [(1, "LF"), (2, "LF"), (3, "LF")],
        )

    def test_pure_crlf(self):
        self.assertEqual(
            lec.scan_bytes(b"a\r\nb\r\n"),
            [(1, "CRLF"), (2, "CRLF")],
        )

    def test_mixed_lf_and_crlf(self):
        self.assertEqual(
            lec.scan_bytes(b"a\nb\r\nc\n"),
            [(1, "LF"), (2, "CRLF"), (3, "LF")],
        )

    def test_lone_cr(self):
        self.assertEqual(
            lec.scan_bytes(b"a\rb\n"),
            [(1, "CR"), (2, "LF")],
        )

    def test_cr_at_end_of_file(self):
        self.assertEqual(lec.scan_bytes(b"a\r"), [(1, "CR")])

    def test_crlf_at_end_of_file(self):
        self.assertEqual(lec.scan_bytes(b"a\r\n"), [(1, "CRLF")])

    def test_empty_file(self):
        self.assertEqual(lec.scan_bytes(b""), [])

    def test_no_trailing_newline(self):
        self.assertEqual(lec.scan_bytes(b"a\nb"), [(1, "LF"), (2, None)])

    def test_single_newline_only(self):
        self.assertEqual(lec.scan_bytes(b"\n"), [(1, "LF")])

    def test_blank_lines(self):
        self.assertEqual(
            lec.scan_bytes(b"\n\r\n\n"),
            [(1, "LF"), (2, "CRLF"), (3, "LF")],
        )

    def test_cr_followed_by_lf_is_one_ending(self):
        self.assertEqual(lec.scan_bytes(b"a\r\n"), [(1, "CRLF")])


class CheckBytesTests(unittest.TestCase):
    def test_clean_lf_passes(self):
        self.assertEqual(lec.check_bytes(b"a\nb\n"), [])

    def test_crlf_fails_under_lf(self):
        self.assertEqual(
            lec.check_bytes(b"a\r\nb\n"),
            [{"line": 1, "found": "CRLF"}],
        )

    def test_cr_fails_under_lf(self):
        self.assertEqual(
            lec.check_bytes(b"a\rb\n"),
            [{"line": 1, "found": "CR"}],
        )

    def test_lf_fails_under_crlf(self):
        self.assertEqual(
            lec.check_bytes(b"a\nb\r\n", expected="CRLF"),
            [{"line": 1, "found": "LF"}],
        )

    def test_pure_crlf_passes_under_crlf(self):
        self.assertEqual(lec.check_bytes(b"a\r\nb\r\n", expected="CRLF"), [])

    def test_empty_passes(self):
        self.assertEqual(lec.check_bytes(b""), [])

    def test_no_trailing_newline_passes(self):
        self.assertEqual(lec.check_bytes(b"a\nb"), [])

    def test_every_wrong_line_reported(self):
        self.assertEqual(
            lec.check_bytes(b"a\r\nb\r\nc\n"),
            [
                {"line": 1, "found": "CRLF"},
                {"line": 2, "found": "CRLF"},
            ],
        )


class BinaryTests(unittest.TestCase):
    def test_null_byte_is_binary(self):
        self.assertTrue(lec.is_binary(b"a\x00b\n"))

    def test_plain_text_is_not_binary(self):
        self.assertFalse(lec.is_binary(b"a\nb\r\nc"))

    def test_empty_is_not_binary(self):
        self.assertFalse(lec.is_binary(b""))

    def test_null_after_probe_is_not_binary(self):
        self.assertFalse(lec.is_binary(b"a" * 9000 + b"\x00"))


class CollectTests(unittest.TestCase):
    def test_clean_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_bytes(Path(tmp) / "a.txt", b"x\ny\n")
            problems, skipped = lec.collect_from_file(path, "LF")
            self.assertEqual(problems, [])
            self.assertFalse(skipped)

    def test_crlf_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_bytes(Path(tmp) / "a.txt", b"x\r\ny\n")
            problems, skipped = lec.collect_from_file(path, "LF")
            self.assertEqual(
                problems,
                [{"line": 1, "found": "CRLF", "error": ""}],
            )
            self.assertFalse(skipped)

    def test_binary_file_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_bytes(Path(tmp) / "a.bin", b"\x00\x01\x02\r\n")
            problems, skipped = lec.collect_from_file(path, "LF")
            self.assertEqual(problems, [])
            self.assertTrue(skipped)

    def test_missing_file_reports_error(self):
        problems, skipped = lec.collect_from_file(
            Path("/no/such/file.txt"), "LF"
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("cannot read file", problems[0]["error"])
        self.assertFalse(skipped)


class CliTests(unittest.TestCase):
    def test_clean_file_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_bytes(Path(tmp) / "a.txt", b"x\ny\n")
            code, out, _err = run_cli([str(path)])
            self.assertEqual(code, 0)
            self.assertIn(
                "OK — 1 file(s) checked, all line endings are LF.", out
            )

    def test_bad_file_exit_one_with_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_bytes(Path(tmp) / "a.txt", b"x\r\ny\nz\r\n")
            code, out, _err = run_cli([str(path)])
            self.assertEqual(code, 1)
            self.assertIn(f"FAIL {path}:1: CRLF line ending", out)
            self.assertIn(f"FAIL {path}:3: CRLF line ending", out)
            self.assertIn(
                "Checked 1 file(s), 2 problem(s) in 1 file(s).", out
            )

    def test_style_crlf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_bytes(Path(tmp) / "a.txt", b"x\ny\n")
            code, out, _err = run_cli(["--style", "crlf", str(path)])
            self.assertEqual(code, 1)
            self.assertIn("LF line ending (expected CRLF)", out)

    def test_style_crlf_passes_crlf_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_bytes(Path(tmp) / "a.txt", b"x\r\ny\r\n")
            code, out, _err = run_cli(["--style", "crlf", str(path)])
            self.assertEqual(code, 0)
            self.assertIn("all line endings are CRLF", out)

    def test_no_args_exit_two(self):
        code, _out, err = run_cli([])
        self.assertEqual(code, 2)
        self.assertIn("no text files to check", err)

    def test_missing_path_exit_two(self):
        code, _out, err = run_cli(["/no/such/file.txt"])
        self.assertEqual(code, 2)
        self.assertIn("no such file or folder", err)

    def test_bad_flag_exits_two(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli(["--nope"])
        self.assertEqual(caught.exception.code, 2)

    def test_bad_style_exits_two(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli(["--style", "cr", "x.txt"])
        self.assertEqual(caught.exception.code, 2)

    def test_version(self):
        code, out, _err = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "line-ending-checker-cli 1.0.0")

    def test_stdin(self):
        code, out, _err = run_cli(["--stdin"], stdin_bytes=b"a\nb\r\n")
        self.assertEqual(code, 1)
        self.assertIn("FAIL <stdin>:2: CRLF line ending", out)
        self.assertIn(
            "Checked 1 file(s), 1 problem(s) in 1 file(s).", out
        )

    def test_stdin_clean(self):
        code, out, _err = run_cli(["--stdin"], stdin_bytes=b"a\nb\n")
        self.assertEqual(code, 0)
        self.assertIn("OK — 1 file(s) checked", out)

    def test_stdin_binary_skipped(self):
        code, _out, err = run_cli(["--stdin"], stdin_bytes=b"\x00\x01")
        self.assertEqual(code, 2)
        self.assertIn("SKIP <stdin>: binary file, not checked", err)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_bytes(Path(tmp) / "a.txt", b"x\r\ny\n")
            code, out, err = run_cli(["--json", str(path)])
            self.assertEqual(code, 1)
            result = json.loads(out)
            self.assertEqual(result["summary"]["checked"], 1)
            self.assertEqual(result["summary"]["problems"], 1)
            self.assertEqual(result["summary"]["expected"], "LF")
            self.assertEqual(
                result["files"][0]["problems"],
                [{"line": 1, "found": "CRLF", "error": ""}],
            )
            self.assertIn("Checked 1 file(s), 1 problem(s)", err)

    def test_json_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_bytes(Path(tmp) / "a.txt", b"x\ny\n")
            code, out, err = run_cli(["--json", str(path)])
            self.assertEqual(code, 0)
            result = json.loads(out)
            self.assertEqual(result["summary"]["problems"], 0)
            self.assertIn("OK — 1 file(s) checked", err)

    def test_empty_file_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_bytes(Path(tmp) / "empty.txt", b"")
            code, out, _err = run_cli([str(path)])
            self.assertEqual(code, 0)
            self.assertIn("OK — 1 file(s) checked", out)

    def test_binary_only_exit_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_bytes(Path(tmp) / "a.bin", b"\x00\x01\r\n")
            code, out, err = run_cli([str(path)])
            self.assertEqual(code, 2)
            self.assertIn(f"SKIP {path}: binary file, not checked", err)

    def test_binary_plus_text_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_bytes(Path(tmp) / "a.bin", b"\x00\x01\r\n")
            path = write_bytes(Path(tmp) / "a.txt", b"x\ny\n")
            code, out, err = run_cli([str(Path(tmp))])
            self.assertEqual(code, 0)
            self.assertIn("SKIP", err)
            self.assertIn("OK — 1 file(s) checked", out)

    def test_folder_walk_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_bytes(root / "top.txt", b"a\r\n")
            write_bytes(root / "sub" / "deep.txt", b"b\r\n")
            code, out, _err = run_cli([str(root)])
            self.assertEqual(code, 1)
            self.assertIn("Checked 2 file(s), 2 problem(s)", out)

    def test_folder_walk_no_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_bytes(root / "top.txt", b"a\r\n")
            write_bytes(root / "sub" / "deep.txt", b"b\r\n")
            code, out, _err = run_cli(["--no-recursive", str(root)])
            self.assertEqual(code, 1)
            self.assertIn("Checked 1 file(s), 1 problem(s)", out)

    def test_git_folder_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_bytes(root / ".git" / "hooks" / "sample.txt", b"a\r\n")
            write_bytes(root / "clean.txt", b"a\n")
            code, out, _err = run_cli([str(root)])
            self.assertEqual(code, 0)
            self.assertIn("OK — 1 file(s) checked", out)

    def test_exclude_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_bytes(root / "gen-bad.txt", b"a\r\n")
            write_bytes(root / "real.txt", b"a\n")
            code, out, _err = run_cli(
                ["--exclude", "gen-*", str(root)]
            )
            self.assertEqual(code, 0)
            self.assertIn("OK — 1 file(s) checked", out)

    def test_several_files_at_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p1 = write_bytes(root / "one.txt", b"a\r\n")
            p2 = write_bytes(root / "two.txt", b"a\n")
            code, out, _err = run_cli([str(p1), str(p2)])
            self.assertEqual(code, 1)
            self.assertIn("Checked 2 file(s), 1 problem(s)", out)

    def test_input_files_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_bytes(Path(tmp) / "a.txt", b"x\r\ny\n")
            before = path.read_bytes()
            run_cli([str(path)])
            self.assertEqual(path.read_bytes(), before)

    def test_empty_folder_exit_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _out, err = run_cli([tmp])
            self.assertEqual(code, 2)
            self.assertIn("no text files to check", err)


class ExamplesTests(unittest.TestCase):
    def test_run_example_matches_sample_output(self):
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        sample = (REPO_ROOT / "examples" / "sample-output.md").read_text()
        self.assertEqual(result.stdout, sample)

    def test_readme_quoted_outputs_match_real_runs(self):
        readme = (REPO_ROOT / "README.md").read_text()
        checks = [
            (["examples/clean.txt"], "OK — 1 file(s) checked, all line endings are LF."),
            (["examples/crlf.txt"], "FAIL examples/crlf.txt:1: CRLF line ending (expected LF)"),
            (["examples/mixed.txt"], "FAIL examples/mixed.txt:4: CR line ending (expected LF)"),
            (["examples/files/"], "Checked 4 file(s), 4 problem(s) in 2 file(s)."),
        ]
        for argv, expected_line in checks:
            code, out, _err = run_cli(argv)
            self.assertIn(expected_line, out)
            self.assertIn(expected_line, readme)


class HygieneTests(unittest.TestCase):
    BANNED = ["TODO", "FIXME", "XXX", "coming soon", "lorem"]

    def _repo_files(self):
        for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
            dirnames[:] = [
                d
                for d in dirnames
                if d not in (".git", "__pycache__", "tests")
            ]
            for name in filenames:
                yield Path(dirpath) / name

    def test_no_placeholder_text(self):
        for path in self._repo_files():
            text = path.read_bytes().decode("utf-8", errors="ignore")
            for word in self.BANNED:
                self.assertNotIn(
                    word, text, f"{word} found in {path}"
                )

    def test_no_absolute_paths(self):
        for path in self._repo_files():
            text = path.read_bytes().decode("utf-8", errors="ignore")
            self.assertNotIn("/home/", text, f"absolute path in {path}")
            self.assertNotIn("/Users/", text, f"absolute path in {path}")

    def test_stdlib_imports_only(self):
        import ast

        tree = ast.parse((REPO_ROOT / "src" / "line_ending_checker.py").read_text())
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    found.add(node.module.split(".")[0])
        self.assertTrue(found, "no imports found at all")
        self.assertEqual(found - ALLOWED_STDLIB, set())

    def test_env_first_in_gitignore(self):
        lines = (REPO_ROOT / ".gitignore").read_text().splitlines()
        self.assertEqual(lines[0], ".env")

    def test_ci_runs_the_tests(self):
        # Plain-text check only: a YAML parser is NOT imported here
        # (Day 11 — a test importing yaml passes locally and fails
        # on a clean GitHub Actions runner). The YAML itself is
        # parsed as a one-off check outside this file.
        ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()
        self.assertIn("actions/checkout@v4", ci)
        self.assertIn("actions/setup-python@v5", ci)
        self.assertIn("python3 tests/test_line_ending_checker.py", ci)


if __name__ == "__main__":
    unittest.main()
