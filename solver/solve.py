from argparse import ArgumentParser
from pathlib import Path
from subprocess import run

from swebench.harness.utils import load_swebench_dataset


def main(
    dataset_name: str,
    split: str,
    instance_ids: list,
    reuse_work_dir: bool,
    max_workers: int,
):
    """
    Run evaluation harness for the given dataset and predictions.
    """

    full_dataset = load_swebench_dataset(dataset_name, split, instance_ids)
    dataset = full_dataset
    print(f"Running {len(dataset)} unevaluated instances...")
    if not dataset:
        print("No instances to run.")
        return

    # TODO: Parallelize this
    # Make inferences
    solver_path = Path(__file__).parent / "solve_instance.py"

    for instance in dataset:
        print(f"Running instance {instance['instance_id']}...")
        solve_args = [
            "python",
            str(solver_path),
            "--dataset_name",
            dataset_name,
            "--instance_id",
            instance["instance_id"],
        ]
        if reuse_work_dir:
            solve_args.append("--reuse_work_dir")

        # Run this as a separate process so that it can change the working directory.
        solve_result = run(solve_args)

        if solve_result.returncode != 0:
            print(f"Failed to run instance {instance['instance_id']}")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--dataset_name",
        default="princeton-nlp/SWE-bench_Lite",
        type=str,
        help="Name of dataset or path to JSON file.",
    )
    parser.add_argument(
        "--split", type=str, default="test", help="Split of the dataset"
    )
    parser.add_argument(
        "--instance_ids",
        nargs="+",
        type=str,
        help="Instance IDs to run (space separated)",
    )
    parser.add_argument(
        "--max_workers",
        type=int,
        default=4,
        help="Maximum number of workers (should be <= 75%% of CPU cores)",
    )
    parser.add_argument(
        "--reuse_work_dir",
        action="store_true",
        help="Reuse the work directory if it exists",
        default=False,
    )

    args = parser.parse_args()
    main(**vars(args))
