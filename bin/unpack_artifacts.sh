#!/usr/bin/env bash

set -e

# Unpack the artifacts to prepare for reporting

# Pre-requisites:
# 1. Run the build_artifacts.sh script to create the artifacts
# OR 
# 1. Run the GitHub Solve workflow to create the artifacts

# Artifacts dir is either "artifacts" or the first shell argument
artifacts_dir="${1}"
if [ -z "${artifacts_dir}" ]; then
  artifacts_dir="artifacts"
fi

# Target dir is either "."" or the second shell argument
target_dir="${2}"
if [ -z "${target_dir}" ]; then
  target_dir="."
fi

mkdir -p "${target_dir}"

# Check that the artifacts directory exists
if [ ! -d "${artifacts_dir}" ]; then
  echo "Artifacts directory not found: ${artifacts_dir}"
  exit 1
fi

if [ ! -d "${target_dir}" ]; then
  echo "Target directory not found: ${target_dir}"
  exit 1
fi

artifacts_dir="$(pwd)/${artifacts_dir}"

cd "${target_dir}"

# If the solve dir exists, it's an error.
if [ -d solve ]; then
  echo "Solve directory already exists. Please remove it before unpacking."
  exit 1
fi

# If the predictions.jsonl file exists, it's an error.
if [ -f predictions.jsonl ]; then
  echo "Predictions file already exists. Please remove it before unpacking."
  exit 1
fi

# If the evaluations directory exists, it's an error.
if [ -d logs/run_evaluation ]; then
  echo "Evaluations directory already exists. Please remove it before unpacking."
  exit 1
fi

# Unpack the artifacts
mkdir -p solve
for artifact in "$artifacts_dir"/solve-*.tar.xz; do
  tar -xJf $artifact
done

# Unpack all predictions and concatenate to predictions.jsonl
for artifact in "$artifacts_dir"/predictions-*.tar.xz; do
  tar -xJf $artifact -O >> predictions.jsonl
done

# Unpack all evaluations to the evaluations directory
for artifact in "$artifacts_dir"/evaluations-*.tar.xz; do
  tar -xJf $artifact
done
