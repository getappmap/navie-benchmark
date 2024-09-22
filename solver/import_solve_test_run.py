from argparse import ArgumentParser
from json import load
import json
from os import getenv, readlink
from pathlib import Path
import shutil
import sys
from typing import Optional
import zipfile

from solver.github_artifacts import download_artifacts

sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

import github
import github.WorkflowRun

from solver.workflow.generate_and_validate_test import (
    TestPatchResult,
    is_optimal_test_patch,
)
from solver.workflow.solution import Solution

OWNER = "getappmap"
REPO = "navie-benchmark"


def local_run_dir(local_run_name: str):
    return Path("data") / "solve_test_runs" / local_run_name


def workflow_run_dir(run_id: int):
    return Path("data") / "solve_test_runs" / "run_id" / str(run_id)


def link_new_test_patches(run_dir: Path, test_patch_dir: Path):
    # Iterate through the test patches and update the data / test_patches directory with a symlink to any
    # new, complete test patches.
    test_patch_dir.mkdir(parents=True, exist_ok=True)
    for test_patch_file in (run_dir / "test_patches").rglob("*.json"):
        instance_id = test_patch_file.stem
        target = test_patch_dir / f"{instance_id}.json"
        if target.exists():
            print(f"Optimal test patch {instance_id} already exists")
            continue

        with test_patch_file.open() as f:
            test_patch: TestPatchResult = json.load(f)

        if not is_optimal_test_patch(test_patch):
            print(f"Skipping non-optimal test patch {instance_id}")
            continue

        link_source = Path("..") / ".." / test_patch_file

        print(f"Importing new optimal test patch {instance_id}")

        target.symlink_to(link_source)

        # Test the symlink
        readlink(target)


def unpack_test_patches(run_dir: Path):
    # Unpack the "test_patch.zip" artifact into the "test_patches" directory
    test_patch_zip = run_dir / "test-patch.zip"

    with zipfile.ZipFile(test_patch_zip, "r") as z:
        z.extractall(run_dir / "test_patches")

    # Iterate through each test_patch file and rename it for its instance.
    # The test patch file name is like test-patch/{instance_id}/navie/test_patch.json
    for test_patch_file in (run_dir / "test_patches").rglob("test_patch.json"):
        instance_id = test_patch_file.parent.parent.name
        with test_patch_file.open() as f:
            test_patch: TestPatchResult = load(f)

        with open(run_dir / "test_patches" / f"{instance_id}.json", "w") as f:
            f.write(json.dumps(test_patch, indent=2))

        # Delete test_patch directory recursively
        shutil.rmtree(test_patch_file.parent.parent)


def download_github_workflow_run(run_id: int):
    github_token = getenv("GITHUB_TOKEN")
    if not github_token:
        raise ValueError("GITHUB_TOKEN is not set")

    g = github.Github(github_token)
    repo = g.get_repo(f"{OWNER}/{REPO}")
    run = repo.get_workflow_run(run_id)
    if not run:
        raise ValueError(f"Run {run_id} not found")

    run_dir = workflow_run_dir(run_id)

    download_artifacts(run_dir, run)

    unpack_test_patches(run_dir)

    print(f"Imported workflow run {run_id}")


def archive_local_run(solve_dir: Path, local_run_name: str, no_solve_dir: bool = False):
    """
    Build the same archive files that would be downloaded from a GitHub Workflow run,
    but use local files in the solve/ directory as the data source. Each
    run includes:

    - predictions-N.zip
    - solutions.zip
    - solve-N.zip
    - test-patch.zip

    Because we are working with local data, N=0 for each of these files.
    """
    run_dir = local_run_dir(local_run_name)

    def zip_predictions():
        prediction_file = Path("predictions.jsonl")
        prediction_file.touch()
        with zipfile.ZipFile(run_dir / "predictions-0.zip", "w") as z:
            z.write(prediction_file, prediction_file)

    def zip_solutions():
        with zipfile.ZipFile(run_dir / "solutions.zip", "w") as z:
            for solution_file in solve_dir.rglob("solution.json"):
                z.write(solution_file, solution_file.relative_to(solve_dir))

    def zip_solve():
        with zipfile.ZipFile(run_dir / "solve-0.zip", "w") as z:
            for file in solve_dir.rglob("*"):
                z.write(file, file.relative_to(solve_dir))

    def zip_test_patches():
        with zipfile.ZipFile(run_dir / "test-patch.zip", "w") as z:
            for test_patch_file in solve_dir.rglob("test_patch.json"):
                z.write(test_patch_file, test_patch_file.relative_to(solve_dir))

    zip_predictions()
    zip_solutions()
    if not no_solve_dir:
        zip_solve()
    zip_test_patches()
    unpack_test_patches(run_dir)

    print(f"Archived local run to {run_dir}")


def main(
    run_id: Optional[int],
    solve_dir: Optional[str],
    local_run_name: str,
    no_download: bool = False,
    no_link: bool = False,
    no_solve_dir: bool = False,
    test_patch_dir: Optional[str] = None,
):
    if not run_id and not solve_dir:
        raise ValueError("Either run_id or solve_dir must be provided")

    if run_id:
        run_dir = workflow_run_dir(run_id)
    else:
        run_dir = local_run_dir(local_run_name)

    run_dir.mkdir(parents=True, exist_ok=True)

    if not no_download:
        if run_id:
            if no_solve_dir:
                print("Ignoring no_solve_dir flag for downloaded run")
            download_github_workflow_run(run_id)
        else:
            assert solve_dir
            archive_local_run(Path(solve_dir), local_run_name, no_solve_dir)

    if not no_link:
        test_patch_dir_path = (
            Path(test_patch_dir) if test_patch_dir else Path("data") / "test_patches"
        )
        link_new_test_patches(run_dir, test_patch_dir_path)


if __name__ == "__main__":
    """
    Import data from a solve run that has been performed to generate test cases.
    The data may be stored locally within the project workspace, or it may be downloaded
    from a GitHub Workflow run.
    """
    parser = ArgumentParser()
    parser.add_argument(
        "--run_id",
        type=int,
        help="The ID of the run to import",
        required=False,
    )
    parser.add_argument(
        "--solve_dir",
        type=str,
        help="The directory containing the solve results",
        required=False,
    )
    parser.add_argument(
        "--local_run_name",
        type=str,
        help="The name of the local run to archive",
        default="local",
    )
    parser.add_argument(
        "--no_download",
        action="store_true",
        help="Skip downloading the artifacts, just unpack and organize the data",
        required=False,
    )
    parser.add_argument(
        "--no_link",
        action="store_true",
        help="Skip linking new test patches",
        required=False,
    )
    parser.add_argument(
        "--no_solve_dir",
        action="store_true",
        help="Skip including the solve directory in the archive",
        required=False,
    )
    parser.add_argument(
        "--test_patch_dir",
        type=str,
        help="The directory in which to store test patches",
    )

    args = parser.parse_args()

    main(**vars(args))
