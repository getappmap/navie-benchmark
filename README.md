## AppMap Navie SWE Bench Solver

This is a SWE Bench solver based on AppMap Navie.

## Build Instructions

### Clone with submodules

```bash
git submodule update --init --recursive
```

### Create and activate virtualenv

Python 3.12 is required.

```bash
virtualenv .venv --python=python3.12
. ./.venv/bin/activate
```

### Install Python dependencies

```bash
pip install ".[dev]"
```

### Build appmap-js

```bash
cd submodules/appmap-js
yarn && yarn build
```

## Solving Locally

### Export LLM key

Options are:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_WEB_CREDENTIALS`

### Export LLM model

Options are:

- `gemini-1.5-pro-002`
- `gpt-4o-2024-08-06`
- `gpt-4o-2024-05-13`
- `gpt-4.1-2025-04-14`
- `o1-preview-2024-09-12`
- `o1-mini-2024-09-12`
- `claude-3-5-sonnet-20240620`
- `claude-3-5-sonnet-20241022`
- `claude-3-7-sonnet-20250219`

### Run the "smoke" subset

```bash
python -m solver.solve \
    --instance_set smoke \
    --limit test_files=2 test_status_retry=2 code_files=2 code_status_retry=2 concurrency=1
```

## Solving in CI

Solvers are provided as GitHub Workflows in the `.github/workflows` directory.

### `solve.yml`

This is a main workflow to run the solver when you want to leverage the pre-generated synthetic test cases. That means that the results of this workflow are not independent of previous runs, which is by design.

It can be triggered manually or via pull request with 'test-solve' label. The `test-solve` label is used for smoke
tests of pull requests.

The workflow:

1. Builds appmap-js dependencies
2. Prepares matrix for parallel execution
3. Runs solver instances across runners
4. Collects and aggregates results
5. Generates final report and artifacts

**Options**

- `use_synthetic_tests`: Whether to use synthetic tests (default true)
- `observe_synthetic_tests`: Whether to observe synthetic test execution (default false)

### `official.yml`

Workflow runs of this workflow are independent of previous runs. Existing synthetic test that are present in the repo are not used by this workflow. They are create by the workflow itself in an initial step. Then, once synthetic tests are
available and no further tests are being discovered, the workflow moves on to finding solutions.

## Run tests

```bash
python -m pytest solver/tests
```

## Logging

Most logging is directed by default to files, otherwise the console output from the project would be very verbose. Also, because the solver is run in parallel, the console output would be interleaved and hard to read.

So, you'll primarily find logs in the `solve` directory. Within this directory, the logs are organized by the instance id. Each Navie command is logged into a separate directory, with the inputs, options, and outputs in separate files.
