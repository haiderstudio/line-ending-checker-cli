#!/bin/sh
# Run the checker on the bundled examples.
# Run from the repo root: sh examples/run-example.sh
# The CRLF and mixed runs exit 1 because the example files carry
# wrong endings on purpose — that is the expected result here.
set -e
cd "$(dirname "$0")/.."
echo "--- check the clean file ---"
python3 src/line_ending_checker.py examples/clean.txt
echo "--- check the CRLF file ---"
python3 src/line_ending_checker.py examples/crlf.txt || true
echo "--- check the mixed file ---"
python3 src/line_ending_checker.py examples/mixed.txt || true
echo "--- check the whole examples/files folder ---"
python3 src/line_ending_checker.py examples/files/ || true
