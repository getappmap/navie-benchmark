from pathlib import Path


def load_instance_set(instance_set: str, instance_ids: set[str] = set()) -> set[str]:

    instance_set_file = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "instance_sets"
        / f"{instance_set}.txt"
    )
    with instance_set_file.open() as f:
        instance_ids.update(
            [id for id in f.read().splitlines() if id and not id.startswith("#")]
        )

    return instance_ids
