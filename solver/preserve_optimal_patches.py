from argparse import ArgumentParser

from solver.load_instance_set import load_instance_set


def main(instance_set: str, predictions_path: str):
    instance_ids = load_instance_set(instance_set)


if __name__ == "__main__":
    """
    Preserves only the optimal patches for a given instance set.

    Run this script after runinng solver.solve. At that point, the solve/ directory
    is full of solve logs. There are also predictions in predictions.jsonl.
     
    What we want to do now is identify all the optimal patches and save the solve logs
    for those patches. This is useful for debugging and for further analysis.
    """
    parser = ArgumentParser()
    parser.add_argument(
        "--instance_set",
        type=str,
        help="Instance set to run",
    )
    parser.add_argument(
        "--predictions_path",
        type=str,
        help="File to write predictions to",
        default="predictions.jsonl",
    )

    args = parser.parse_args()
    main(**vars(args))
