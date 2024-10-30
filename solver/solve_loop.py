import os
import subprocess
from pathlib import Path
import shutil
from argparse import ArgumentParser
import sys
from typing import Callable, Optional, TypedDict

from solver.load_instance_set import load_instance_set
from solver.solve import DATASET_NAME

sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from solver.cli import configure_runner_index, load_dataset, select_instances_for_runner


class TestSolveResult(TypedDict):
    new_test_patch_count: int


class CodeSolveResult(TypedDict):
    pass


def load_instance_ids(
    instance_set: str, num_runners: Optional[int], runner_index: Optional[int]
) -> list[str]:
    dataset = load_dataset(DATASET_NAME, list(load_instance_set(instance_set)))
    dataset = select_instances_for_runner(dataset, num_runners, runner_index)
    return [instance["instance_id"] for instance in dataset]


def enumerate_test_patch_files() -> list[Path]:
    return list(Path("data/test_patches").glob("*.json"))


def enumerate_test_patch_instance_ids() -> set[str]:
    return set(p.stem for p in enumerate_test_patch_files())


def count_test_patches(instance_ids: list[str]) -> int:
    test_patch_instance_ids = enumerate_test_patch_instance_ids()
    return len(test_patch_instance_ids.intersection(instance_ids))


def ignore_source_dir(root_dir: str) -> Callable[[str, list[str]], list[str]]:
    """
    Returns a shutil.copytree-compatible ignore function.
    Ignores the 'source' directory within the directory being copied.
    """

    def ignore_source_dir_fn(dir: str, entries: list[str]) -> list[str]:
        if dir == root_dir and "source" in entries:
            return ["source"]

        return []

    return ignore_source_dir_fn


def test_solver(
    instance_set: str,
) -> Callable[[int, float], TestSolveResult]:
    def solve(context_tokens: int, temperature: float) -> TestSolveResult:
        solve_test_limits = f"test_files=3 test_status_retry=3 code_files=0 code_status_retry=0 context_tokens={context_tokens}".split(
            " "
        )

        instance_ids = load_instance_ids(instance_set, None, None)
        if not instance_ids:
            print("[solve] No instances to run.")
            return TestSolveResult(new_test_patch_count=0)

        initial_test_patch_count = count_test_patches(instance_ids)

        solve_test_arguments = [
            "python",
            "-m",
            "solver.solve",
            "--instance_set",
            instance_set,
            "--limit",
        ]
        solve_test_arguments.extend(solve_test_limits)

        subprocess.run(
            solve_test_arguments,
            env={**os.environ, "APPMAP_NAVIE_TEMPERATURE": str(temperature)},
        )

        # Collect optimal test patches
        subprocess.run(
            ["python", "-m", "solver.import_solve_test_run", "--solve_dir", "solve"]
        )

        subprocess.run(
            [
                "python",
                "-m",
                "solver.filter_solutions_from_instance_set",
                "--instance_set",
                instance_set,
                "--output_instance_set",
                instance_set,
                "--filter_by",
                "test",
            ]
        )

        updated_test_patch_count = count_test_patches(instance_ids)
        new_test_patch_count = updated_test_patch_count - initial_test_patch_count

        print(f"Number of new test patches: {new_test_patch_count}")

        return TestSolveResult(new_test_patch_count=new_test_patch_count)

    return solve


def code_solver(
    instance_set: str,
) -> Callable[[int], CodeSolveResult]:
    def solve(context_tokens: int) -> CodeSolveResult:
        # By enumerating test files here, we enable the code solver to find and utilize a pass-to-pass test even when there
        # are no optimal test patches for a given instance.
        solve_code_limits = f"test_files=3 test_status_retry=1 code_files=3 code_status_retry=3 context_tokens={context_tokens}".split(
            " "
        )
        solve_code_arguments = [
            "python",
            "-m",
            "solver.solve",
            "--instance_set",
            instance_set,
            "--limit",
        ]
        solve_code_arguments.extend(solve_code_limits)

        subprocess.run(solve_code_arguments)

        return CodeSolveResult()

    return solve


def evaluate(
    instance_set: str,
) -> Callable[[], None]:
    def evaluate_fn() -> None:
        subprocess.run(
            [
                "python",
                "-m",
                "swebench.harness.run_evaluation",
                "--predictions_path",
                "predictions.jsonl",
                "--run_id",
                instance_set,
            ]
        )

    return evaluate_fn


def copy_solve_dir(type: str, source_dir: Path, target_dir: Path) -> None:
    if not source_dir.exists():
        print(f"WARNING solve {type} directory '{source_dir}' does not exist")
        return

    if target_dir.exists():
        print(f"WARNING solve {type} directory '{target_dir}' already exists")
        return

    shutil.copytree(
        str(source_dir), target_dir, ignore=ignore_source_dir(str(source_dir))
    )


def archive_test_logs(archive_dir: Path) -> None:
    """
    Copies the solve logs of optimal test patches to the directory archive/solve_test.
    While copying, removes the source directory from each test patch directory.
    After saving these logs, the solve directory is erased.
    """
    print(f"Saving solve logs for test patches")

    solve_dir = Path("solve")
    if not solve_dir.exists():
        print(f"WARNING solve_test directory '{solve_dir}' does not exist")
        return

    predictions_file = Path("predictions.jsonl")
    test_log_dir = archive_dir / "solve_test"
    # The test solver can run multiple times, so it's not an error if this directory already exists.
    test_log_dir.mkdir(parents=True, exist_ok=True)

    # Enumerate all test patch solve logs. Move the corresponding directory from solve/{instance} to solve_test/{instance}
    for instance_id in enumerate_test_patch_instance_ids():
        copy_solve_dir("test", solve_dir / instance_id, test_log_dir / instance_id)

    print(f"Resetting the solve directory")
    shutil.rmtree(str(solve_dir), ignore_errors=True)
    if predictions_file.exists():
        print("Removing predictions.jsonl, because test predictions are not evaluated")
        predictions_file.unlink()


def archive_code_logs(archive_dir: Path) -> None:
    """
    Copies the solve logs of code patches, and the predictions.jsonl file, to the directory archive/solve_code.
    After saving these logs, the solve directory is erased.
    """

    print("Saving solve logs for code patches")

    solve_dir = Path("solve")
    target_dir = archive_dir / "solve_code"

    # Code solver is currently designed to run only once per runner.
    if target_dir.exists():
        print(f"WARNING solve_code directory '{target_dir}' already exists")
        print("Skipping archive of code logs")
        return

    predictions_file = Path("predictions.jsonl")

    if not solve_dir.exists():
        print(f"WARNING solve_code directory '{solve_dir}' does not exist")
        return

    target_dir.mkdir(parents=True, exist_ok=True)

    for instance_dir in solve_dir.glob("*"):
        copy_solve_dir("code", instance_dir, target_dir / instance_dir.name)

    if predictions_file.exists():
        shutil.copy(predictions_file, target_dir)

    print("Resetting the solve directory")
    shutil.rmtree(str(solve_dir), ignore_errors=True)


def archive_evaluate_logs(archive_dir: Path, instance_set: str) -> None:
    """
    Copies the evaluation logs from logs/run_evaluation to the directory archive/evaluation.
    Copies the navie_{instance_set}.json file and predictions.jsonl file to the directory archive/evaluation.
    After saving these logs, the logs/run_evaluation directory is erased, and the navie_{instance_set}.json file
    and predictions.jsonl file are deleted.
    """

    print("Saving evaluation logs")

    evaluation_dir = Path("logs") / "run_evaluation"
    target_dir = archive_dir / "evaluation"

    # Evaluation is currently designed to run only once per runner.
    if target_dir.exists():
        print(f"WARNING evaluation archive directory '{target_dir}' already exists")
        print("Skipping archive of evaluation logs")
        return

    predictions_file = Path("predictions.jsonl")
    target_dir.mkdir(parents=True, exist_ok=True)

    def skip_image_build_dir(dir: str, entries: list[str]) -> list[str]:
        # Work around:
        # shutil.Error: [('logs/run_evaluation/smoke/navie_082024+gpt-4o-2024-08-06/django__django-14559/image_build_dir', 'archive/evaluation/django__django-14559/image_build_dir',
        # "[Errno 2] No such file or directory: 'logs/run_evaluation/smoke/navie_082024+gpt-4o-2024-08-06/django__django-14559/image_build_dir'")]
        return ["image_build_dir"] if "image_build_dir" in entries else []

    for instance_dir in evaluation_dir.glob("*/*/*"):
        shutil.copytree(
            str(instance_dir),
            target_dir / instance_dir.name,
            ignore=skip_image_build_dir,
        )

    for src_file in Path(".").glob(f"navie_*.{instance_set}.json"):
        shutil.copy(src_file, target_dir / src_file.name)

    print(f"Copying predictions to {target_dir / 'predictions.jsonl'}")
    shutil.copy(predictions_file, target_dir / "predictions.jsonl")

    print(f"Resetting the evaluation directory and evaluation file")
    shutil.rmtree(str(evaluation_dir), ignore_errors=True)
    for src_file in Path(".").glob(f"navie_*.{instance_set}.json"):
        src_file.unlink()
    print("Removing predictions.jsonl")
    if predictions_file.exists():
        predictions_file.unlink()


def confirm(prompt: str) -> bool:
    if sys.stdin.isatty():
        print(prompt)
        return input().lower() == "y"
    else:
        return True


def write_working_set(
    instance_set: str, num_runners: Optional[int], runner_index: Optional[int]
) -> str:
    instance_ids = load_instance_ids(instance_set, num_runners, runner_index)
    new_instance_set = f"{instance_set}_working"
    new_instance_set_file = Path(f"data/instance_sets/{new_instance_set}.txt")
    with new_instance_set_file.open("w") as f:
        f.write("\n".join(sorted(instance_ids)))
    return new_instance_set


def solve_loop(
    instance_set: str,
    context_tokens: int,
    context_token_limit_increase: int,
    temperature: float,
    temperature_increase: float,
    test_patch_solve_threshold: int,
    use_synthetic_tests: bool,
    num_runners: Optional[int] = None,
    runner_index: Optional[int] = None,
    min_test_solve_iterations: int = 1,
    max_test_solve_iterations: int = 5,
    no_solve_test: bool = False,
    no_solve_code: bool = False,
    no_evaluate: bool = False,
):
    if not use_synthetic_tests:
        if confirm("Are you sure you want to remove synthetic tests? (y/n)"):
            print("Removing synthetic tests by deleting data/test_patches")
            shutil.rmtree("data/test_patches", ignore_errors=True)

    print(f"Building working set for instance set '{instance_set}'")
    new_instance_set = write_working_set(instance_set, num_runners, runner_index)

    print(
        f"Collected {len(load_instance_ids(new_instance_set, num_runners, runner_index))} instances"
    )

    test_solver_fn = test_solver(new_instance_set)
    code_solver_fn = code_solver(new_instance_set)
    evaluate_fn = evaluate(instance_set)

    def solve_test():
        iteration_count = 0
        test_context_tokens = context_tokens
        test_temperature = temperature
        while True:
            iteration_count += 1

            test_solution = test_solver_fn(test_context_tokens, test_temperature)

            if iteration_count == max_test_solve_iterations:
                print(f"Maximum iterations ({max_test_solve_iterations}) reached.")
                break

            if iteration_count >= min_test_solve_iterations:
                print(
                    f"Minimum iterations ({min_test_solve_iterations}) reached (after {iteration_count})."
                )

                if test_solution["new_test_patch_count"] < test_patch_solve_threshold:
                    new_test_patch_count = test_solution["new_test_patch_count"]
                    print(
                        f"Number of new optimal test patches ({new_test_patch_count}) is below threshold ({test_patch_solve_threshold}). No more test patch attempts will be run."
                    )
                    break

            test_context_tokens += int(
                test_context_tokens * context_token_limit_increase / 100
            )
            print(f"Increasing context tokens to {test_context_tokens}")

            if temperature_increase != 0:
                test_temperature += temperature_increase
                print(f"Increasing temperature to {test_temperature}")

    archive_dir = Path("archive")

    if no_solve_test:
        print("Skipping test solver due to no_solve_test flag")
    else:
        solve_test()
        archive_test_logs(archive_dir)

    print(f"Resetting the instance set and running code solver")
    write_working_set(instance_set, num_runners, runner_index)

    if no_solve_code:
        print("Skipping code solver due to no_solve_code flag")
    else:
        code_solver_fn(context_tokens)
        archive_code_logs(archive_dir)

    if no_evaluate:
        print("Skipping evaluation due to no_evaluate flag")
    else:
        evaluate_fn()
        archive_evaluate_logs(archive_dir, instance_set)


if __name__ == "__main__":
    parser = ArgumentParser(description="Run the solver and process results.")
    parser.add_argument(
        "--instance_set", type=str, required=True, help="Instance set to use"
    )
    parser.add_argument(
        "--context_tokens",
        type=int,
        default=8000,
        help="Context token limit",
    )
    parser.add_argument(
        "--temperature", type=float, default=0, help="Initial temperature"
    )
    parser.add_argument(
        "--temperature_increase",
        type=float,
        default=0,
        help="Temperature increase per iteration",
    )
    parser.add_argument(
        "--test_patch_solve_threshold",
        type=int,
        default=1,
        help="Threshold for solving test patches",
    )
    parser.add_argument(
        "--context_token_limit_increase",
        type=int,
        default="10",
        help="Context token limit increase percentage",
    )
    parser.add_argument(
        "--use_synthetic_tests", action="store_true", help="Use synthetic tests"
    )
    parser.add_argument(
        "--min_test_solve_iterations",
        type=int,
        default=1,
        help="Minimum number of test solve iterations to run",
    )
    parser.add_argument(
        "--max_test_solve_iterations",
        type=int,
        default=5,
        help="Maximum number of test solve iterations to run",
    )
    parser.add_argument(
        "--no_solve_test",
        action="store_true",
        help="Skip solving test patches",
    )
    parser.add_argument(
        "--no_solve_code",
        action="store_true",
        help="Skip solving code patches",
    )
    parser.add_argument(
        "--no_evaluate",
        action="store_true",
        help="Skip evaluation",
    )

    configure_runner_index(parser)

    args = parser.parse_args()
    solve_loop(**vars(args))
