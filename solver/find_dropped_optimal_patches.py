from argparse import ArgumentParser
import json
from pathlib import Path
import re
import sys
from typing import Generator, Optional
import zipfile

from solver.prepare_predictions import find_prediction_in_zip_archive

sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))


def debug_msg(msg: str = ""):
    sys.stderr.write(f"{msg}\n")


def match_optimal_patch(line: str) -> Optional[str]:
    # Example: 2024-09-16 18:23:50,545 - INFO - Optimal code patch generated: 1
    match = re.search(r"Optimal code patch generated: [0-9]+", line)
    if match:
        return match.group()
    return None


def find_running_test_log_entry(line: str) -> Optional[tuple]:
    # Example: 2024-09-16 18:23:50,545 - INFO - [run-test] (django__django-15851) Running tests tests/dbshell/test_postgresql.py in /Users/kgilpin/source/appland/navie-benchmark/solve/django__django-15851/navie/solve-code-1/generate-code/attempt-1/run-test/pass-to-pass
    pattern = r"\[run-test\] \(([^)]+)\) Running tests (?:.*) in ([^ ]+)"
    match = re.search(pattern, line)
    if match:
        instance_id = match.group(1)
        test_log_path = match.group(2).strip()
        return (instance_id, test_log_path)


def reverse_search_for_test_log_path(
    data: list[bytes],
    index: int,
) -> Optional[tuple]:
    for j in range(index, 0, -1):
        test_log_path = find_running_test_log_entry(
            data[j].decode("utf-8", errors="ignore")
        )
        if test_log_path:
            return test_log_path

    return None


def newer_solution_exists_for_instance_id(instance_id: str, timestamp: float) -> bool:
    code_patches_dir = Path("data") / "code_patches"
    code_patch_file = code_patches_dir / f"{instance_id}.json"
    if code_patch_file.exists():
        code_patch_file_timestamp = code_patch_file.stat().st_mtime
        return code_patch_file_timestamp > timestamp

    return False


def main(log_patches: bool):
    unique_instance_ids = set()
    patch_update_by_instance_id = {}
    patch_count = 0
    run_id_dir = Path("data") / "solve_code_runs" / "run_id"
    run_id_dirs = list(run_id_dir.iterdir())
    # Iterate in reverse order of directory name, collecting the most recent patch for each instance id
    run_id_dirs.sort(key=lambda x: x.name, reverse=True)
    for run_id_dir in run_id_dirs:
        # Enumerate solve-*.zip files.
        # Within each solve-*.zip file, enumerate solve.log files.
        zip_files = list(run_id_dir.glob("solve-*.zip"))
        for zip_file in zip_files:
            with zipfile.ZipFile(zip_file, "r") as z:
                optimal_test_runs: list[tuple] = []
                for name_str in z.namelist():
                    name = Path(name_str)
                    if name.name == "solve.log":
                        with z.open(name_str) as zf:
                            data = zf.readlines()
                            for i, line_bytes in enumerate(data):
                                line = line_bytes.decode("utf-8", errors="ignore")
                                if "Optimal code patch generated" in line:
                                    search_result = reverse_search_for_test_log_path(
                                        data, i
                                    )
                                    if search_result:
                                        instance_id, test_log_path = search_result
                                        optimal_test_runs.append(
                                            (instance_id, test_log_path)
                                        )

                if optimal_test_runs:

                    def enumerate_code_patches_in_run_test_dir(
                        dir: str,
                    ) -> Generator[str, None, None]:
                        for name_str in z.namelist():
                            name_dir = Path(name_str).parent
                            if (
                                str(name_dir) in dir
                                and Path(name_str).name.startswith("code_")
                                and Path(name_str).name.endswith(".patch")
                            ):
                                yield name_str

                    for instance_id, test_log_path in optimal_test_runs:
                        for name_str in enumerate_code_patches_in_run_test_dir(
                            test_log_path
                        ):
                            patch_contents = z.read(name_str).decode("utf-8", "ignore")
                            navie_log_dir = Path(
                                name_str
                            ).parent.parent.parent.parent.parent.parent
                            code_patch_file = navie_log_dir / "code.patch"
                            solution_file = navie_log_dir / "solution.json"
                            try:
                                patch_contents_offical = z.read(
                                    str(code_patch_file)
                                ).decode("utf-8", "ignore")
                            except KeyError:
                                if log_patches:
                                    debug_msg(
                                        f"Official patch not found: {code_patch_file}"
                                    )
                                patch_contents_offical = ""

                            if patch_contents_offical != patch_contents:
                                patch_count += 1
                                if log_patches:
                                    debug_msg(
                                        f"Official patch does not match patch for instance {instance_id} in test run: {code_patch_file}"
                                    )
                                timestamp = zip_file.stat().st_mtime
                                if newer_solution_exists_for_instance_id(
                                    instance_id, timestamp
                                ):
                                    debug_msg(
                                        f"Updated optimal solution exists for instance {instance_id}"
                                    )
                                elif instance_id not in patch_update_by_instance_id:

                                    def read_solution(
                                        solution_file: Path,
                                    ) -> Optional[dict]:
                                        try:
                                            solution_str = z.read(
                                                str(solution_file)
                                            ).decode("utf-8", "ignore")
                                        except KeyError:
                                            print(
                                                f"Solution not found: {solution_file}"
                                            )
                                            return None

                                        return json.loads(solution_str)

                                    solution = read_solution(solution_file)
                                    if solution:
                                        solution["code_patch"] = patch_contents
                                        solution["code_patch_issue-46"] = (
                                            patch_contents_offical
                                        )
                                        prediction = None
                                        predictions_files = run_id_dir.glob(
                                            "predictions-*.zip"
                                        )
                                        for predictions_file in predictions_files:
                                            prediction = find_prediction_in_zip_archive(
                                                predictions_file,
                                                solution["instance_id"],
                                            )
                                            if prediction:
                                                break

                                        assert prediction
                                        prediction["model_patch"] = patch_contents
                                        patch_update_by_instance_id[instance_id] = (
                                            patch_contents_offical,
                                            patch_contents,
                                            solution,
                                            prediction,
                                        )
                                        unique_instance_ids.add(instance_id)
                                        if log_patches:
                                            debug_msg("Reported patch:")
                                            debug_msg(patch_contents_offical)
                                            debug_msg()
                                            debug_msg("Patch in test run:")
                                            debug_msg(patch_contents)
                                            debug_msg()
                                else:
                                    debug_msg(
                                        f"Multiple patches detected for instance {instance_id}"
                                    )

    debug_msg(f"Total patches that do not match official patches: {patch_count}")
    debug_msg(f"Unique instance ids to be updated: {len(unique_instance_ids)}")

    print("Storing updated solutions:")
    predictions_dir = Path("data") / "predictions_issue-46"
    predictions_dir.mkdir(parents=True, exist_ok=True)
    for instance_id in sorted(unique_instance_ids):
        print(f"  {instance_id}")
        solution_file = Path("data") / "code_patches" / f"{instance_id}.json"
        _, patch_contents, solution, prediction = patch_update_by_instance_id[
            instance_id
        ]
        with solution_file.open("w") as f:
            f.write(json.dumps(solution, indent=2))
        prediction_file = predictions_dir / f"{instance_id}.json"
        with prediction_file.open("w") as f:
            f.write(json.dumps(prediction, indent=2))

    debug_msg("Done!")


if __name__ == "__main__":
    """
    Finds optimal patches by scanning through the solve.log. Compares the optimal patch detected in this way with
    the reported optimal patch.
    """
    parser = ArgumentParser()
    parser.add_argument(
        "--log_patches",
        action="store_true",
        help="Print the reported and updated patches as they are found",
    )

    args = parser.parse_args()
    main(**vars(args))
