from argparse import ArgumentParser
import json
from pathlib import Path
import sys

from swebench.harness.run_evaluation import report_file_name


def main(
    predictions_path: str,
    run_id: str,
) -> None:
    """
    Print the name of the evaluations file for a given set of parameters.
    Companion script to swebench.harness.run_evaluations.
    """
    predictions_p = Path(predictions_path)
    with predictions_p.open() as f:
        predictions_str = f.read()

    predictions_jsonl = predictions_str.splitlines()
    if not predictions_jsonl:
        print(f"No predictions found in {predictions_path}", file=sys.stderr)
        return

    first_prediction = json.loads(predictions_jsonl[0])

    model_name = first_prediction["model_name_or_path"]
    if not model_name:
        print("No model name found in predictions", file=sys.stderr)
        return

    print(report_file_name(model_name, run_id))


if __name__ == "__main__":
    """
    Print the name of the evaluations file for a given set of parameters.
    Companion script to swebench.harness.run_evaluations.
    """

    parser = ArgumentParser()
    parser.add_argument(
        "--predictions_path",
        type=str,
        help="Path to the predictions file",
    )
    parser.add_argument(
        "--run_id", type=str, required=True, help="Run ID - identifies the run"
    )

    args = parser.parse_args()
    main(**vars(args))
