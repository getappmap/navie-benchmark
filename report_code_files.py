from argparse import ArgumentParser
import csv
import pandas as pd
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent / "solver"))
sys.path.append(str(Path(__file__).parent / "submodules" / "navie-editor"))

from solver.workflow.patch import Patch

PARQUET_FILE = "SWE-bench_verified.parquet"


def main(directory: str):

    # Read the parquet file
    df = pd.read_parquet(PARQUET_FILE)

    code_files = []
    dir_path = Path(directory)
    for search_output in dir_path.rglob("search.output.txt"):
        with search_output.open() as f:
            content = f.read()
            instance_id = search_output.parent.parent.parent.parent.name
            print(instance_id)
            lines = content.splitlines()

            # Strip everything from the path from the lowest "source" directory
            def strip_path(path: str) -> str:
                parts = path.split("/")
                if "source" not in parts:
                    return path

                source_index = parts.index("source")
                return "/".join(parts[source_index + 1 :])

            paths = [strip_path(path) for path in lines]
            paths = sorted(paths)
            code_files.append(
                {"instance_id": instance_id, "code_files": "\n".join(paths)}
            )

    code_files_sorted = sorted(code_files, key=lambda x: x["instance_id"])
    with (Path("data") / "instance_sets" / "verified.txt").open("r") as f:
        verified_set = f.read().splitlines()
    verified_set = sorted(verified_set)

    report_file = Path("code_files.csv")
    with report_file.open("w") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "instance_id",
                "code_files",
                "gold_code_files",
                "code_files_match",
                "code_files_extra",
                "code_files_missing",
            ],
        )
        writer.writeheader()
        code_file_index = 0
        for instance_id in verified_set:
            # Filter the dataframe for the specific instance_id and print the "patch" field
            patch_str = df.loc[df["instance_id"] == instance_id, "patch"]
            if not len(patch_str):
                print(f"No patch found for instance_id: {instance_id}")

            # Get the first patch item
            patch = Patch(patch_str.iloc[0])
            print(f"Patch files: {patch.list_files()}")

            if (
                code_file_index < len(code_files_sorted)
                and code_files_sorted[code_file_index]["instance_id"] == instance_id
            ):
                code_files_match = (
                    True
                    if patch.list_files()
                    == code_files_sorted[code_file_index]["code_files"].splitlines()
                    else False
                )
                code_files_extra = len(
                    set(patch.list_files())
                    - set(code_files_sorted[code_file_index]["code_files"].splitlines())
                )
                code_files_missing = len(
                    set(code_files_sorted[code_file_index]["code_files"].splitlines())
                    - set(patch.list_files())
                )

                writer.writerow(
                    {
                        "instance_id": instance_id,
                        "code_files": code_files_sorted[code_file_index]["code_files"],
                        "gold_code_files": "\n".join(patch.list_files()),
                        "code_files_match": code_files_match,
                        "code_files_extra": code_files_extra,
                        "code_files_missing": code_files_missing,
                    }
                )
                code_file_index += 1
            else:
                writer.writerow({"instance_id": instance_id})


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--directory",
        type=str,
        help="Directory to search for code files",
        required=True,
    )

    args = parser.parse_args()

    main(**vars(args))
