from argparse import ArgumentParser
from pathlib import Path
import shutil
import pandas as pd
import zipfile

# Adjust the path to your actual SWE-Bench_verified parquet file and the specific instance_id
PARQUET_FILE = "SWE-bench_verified.parquet"


def main(instance_id: str):
    # Read the parquet file
    df = pd.read_parquet(PARQUET_FILE)

    issue = df.loc[df["instance_id"] == instance_id, "problem_statement"]
    if not issue.empty:
        print(issue.iloc[0])
    else:
        print(f"No issue found for instance_id: {instance_id}")

    # Filter the dataframe for the specific instance_id and print the "patch" field
    patch = df.loc[df["instance_id"] == instance_id, "patch"]

    # Print the patch field
    if not patch.empty:
        print("Gold patch:")
        print(patch.iloc[0])
    else:
        print(f"No patch found for instance_id: {instance_id}")
    print("")

    solve_code_runs_dir = Path("data") / "solve_code_runs"
    solve_zip_files = []
    for run_dir in solve_code_runs_dir.iterdir():
        if run_dir.is_dir():
            for run_results_dir in run_dir.iterdir():
                run_id = run_results_dir.name
                run_solve_zip_files = list(run_results_dir.rglob("solve-*.zip"))
                for solve_zip_file in run_solve_zip_files:
                    instances_in_zip = set()
                    with zipfile.ZipFile(solve_zip_file, "r") as zip_ref:
                        files = {Path(f).parts[0] for f in zip_ref.namelist()}
                        instances_in_zip.update(files)
                    if instance_id in instances_in_zip:
                        print(
                            f"Instance id found in Run ID: {run_id}, File: {solve_zip_file}"
                        )
                        solve_zip_files.append(solve_zip_file)

    for solve_zip_file in solve_zip_files:
        run_id = solve_zip_file.parent.name

        analyze_dir = Path("analyze") / instance_id / run_id
        print(f"Unpacking solve logs to to {analyze_dir}")
        print("")
        analyze_dir.mkdir(exist_ok=True, parents=True)
        shutil.rmtree(analyze_dir)

        with zipfile.ZipFile(solve_zip_file, "r") as zip_ref:
            # Extract the specified solve-*.json files
            for file in zip_ref.namelist():
                if instance_id in file:
                    zip_ref.extract(file, analyze_dir)

        navie_code_patch_file = analyze_dir.rglob("*/navie/code.patch")
        if not navie_code_patch_file:
            print("No navie code patch found")

        for file in navie_code_patch_file:
            print(f"Navie code patch for run {run_id}:")
            with file.open() as f:
                print(f.read())


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--instance_id", type=str, help="Instance ID to run", required=True
    )

    args = parser.parse_args()

    main(**vars(args))
