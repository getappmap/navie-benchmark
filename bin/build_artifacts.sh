#!/usr/bin/env bash

set -e

# Simulate building artifacts the way that the GitHub Solve workflow does. This is used to test that the
# unpacking and reporting of artifacts works correctly in the GitHub Solve workflow.

# Prerequisites (see solve.yml for details):
# 1. solver.solve with the "smoke" instance set
# 2. swebench.harness.run_evaluation
# 3.
# evaluations_file_name=$(
#   python -m solver.evaluations_file_name  \
#     --run_id smoke \
#     --predictions_path predictions.jsonl
# )
# cp "${evaluations_file_name}" evaluations.json


# Create the artifacts directory if it doesn't exist
rm -rf .artifacts
mkdir -p .artifacts

# Create a tar xz artifact for predictions.jsonl
tar -cJf .artifacts/predictions-1.jsonl.tar.xz predictions.jsonl
tar -cJf .artifacts/predictions-2.jsonl.tar.xz predictions.jsonl

# Similarly for evaluations.json
tar -cJf .artifacts/evaluations-1.tar.xz logs/run_evaluation/
tar -cJf .artifacts/evaluations-2.tar.xz logs/run_evaluation/

# First batch of solve logs
tar --exclude='solve/source' -cJf .artifacts/solve-1.tar.xz solve/django__django-13658 solve/pytest-dev__pytest-7490
# Second batch of solve logs
tar --exclude='solve/source' -cJf .artifacts/solve-2.tar.xz solve/scikit-learn__scikit-learn-13779 solve/sympy__sympy-22714
