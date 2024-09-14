from argparse import ArgumentParser
from http.client import HTTPMessage
from json import load
import json
from os import getenv, readlink
from pathlib import Path
import shutil
import sys
from typing import Tuple
import urllib.request

from solver.github_artifacts import download_artifacts

sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

import github
import github.WorkflowRun

from solver.workflow.solution import Solution, meets_score_threshold

OWNER = "getappmap"
REPO = "navie-benchmark"


def import_workflow_run(run: github.WorkflowRun.WorkflowRun, no_download: bool = False):
    target_dir = Path("data") / "solve_code_runs" / "run_id" / str(run.id)
    target_dir.mkdir(parents=True, exist_ok=True)

    if not no_download:
        download_artifacts(target_dir, run)

    # Unpack the "solutions.zip" artifact into the "code_patches" directory
    solutions_zip = target_dir / "solutions.zip"

    def unpack_solutions():
        import zipfile

        with zipfile.ZipFile(solutions_zip, "r") as z:
            z.extractall(target_dir / "code_patches")

    unpack_solutions()

    # Iterate through each solution file and reformulate it as a test patch
    for solution_file in (target_dir / "code_patches").rglob("solution.json"):
        with solution_file.open() as f:
            solution: Solution = load(f)

        instance_id = solution["instance_id"]
        with open(target_dir / "code_patches" / f"{instance_id}.json", "w") as f:
            f.write(json.dumps(solution, indent=2))

        # Delete solution_file parent directory recursively
        shutil.rmtree(solution_file.parent.parent)

    # Iterate through the code patches and update the data / code_patches directory with a symlink to any
    # new, complete test patches.
    for code_patch_file in (target_dir / "code_patches").rglob("*.json"):
        instance_id = code_patch_file.stem
        target = Path("data") / "code_patches" / f"{instance_id}.json"
        if target.exists():
            continue

        with code_patch_file.open() as f:
            solution: Solution = load(f)

        if not meets_score_threshold(solution["code_patch_score"]):
            continue

        link_source = Path("..") / ".." / code_patch_file

        print(f"Importing new optimal code patch {instance_id}")
        print(f"Link target: {target}")
        print(f"Link source: {link_source}")

        target.symlink_to(link_source)

        # Test the symlink
        readlink(target)


def main(run_id: int, no_download: bool = False):
    github_token = getenv("GITHUB_TOKEN")
    if not github_token:
        raise ValueError("GITHUB_TOKEN is not set")

    g = github.Github(github_token)
    repo = g.get_repo(f"{OWNER}/{REPO}")
    run = repo.get_workflow_run(run_id)
    if not run:
        raise ValueError(f"Run {run_id} not found")

    import_workflow_run(run, no_download)

    print(f"Imported workflow run {run_id}")


if __name__ == "__main__":
    """
    Import data from a GitHub Workflow run that has been performed to generate code solutions.
    """
    parser = ArgumentParser()
    parser.add_argument(
        "--run_id",
        type=int,
        help="The ID of the run to import",
        required=True,
    )
    parser.add_argument(
        "--no_download",
        action="store_true",
        help="Skip downloading the artifacts. Just unpack and organize the data",
    )

    args = parser.parse_args()

    main(**vars(args))
