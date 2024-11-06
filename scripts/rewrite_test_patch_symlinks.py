from hashlib import md5
from os import readlink
from pathlib import Path


def rewrite_symlink(symlink_path: Path):
    """
    Checks if the parent directory of the target file contains a solve-*.zip file.
    If not, searches through data/solve_test_runs tree for a json file with the same
    checksum that fulfills this condition and rewrites the symlink to point to that file instead.
    """

    original_target = Path(symlink_path.parent, readlink(symlink_path))
    instance_id = symlink_path.stem

    # Calculate checksum of the original target file
    with original_target.open("rb") as f:
        original_checksum = md5(f.read()).hexdigest()

    # Check if the original target's parent directory contains a solve-*.zip file
    has_solve_zip = any(original_target.parent.parent.glob("solve-*.zip"))

    if has_solve_zip:
        print(f"Symlink {symlink_path} already points to a valid target.")
        return

    # Search for a replacement target
    replacement_target = None
    for run_dir in Path("data/solve_test_runs").rglob("*"):
        for test_patch_file in run_dir.rglob(f"{instance_id}.json"):
            # Calculate checksum of the potential replacement target
            with test_patch_file.open("rb") as f:
                test_patch_checksum = md5(f.read()).hexdigest()

            # Check if checksums match and parent directory contains any solve-*.zip that contains trajectory
            if (
                test_patch_checksum == original_checksum
                and path_solve_contains_trajectory(
                    test_patch_file.parent.parent, instance_id
                )
            ):
                replacement_target = test_patch_file.relative_to(
                    symlink_path.parent, walk_up=True
                )
                break
        if replacement_target:
            break

    if replacement_target:
        print(f"Rewriting symlink {symlink_path} to {replacement_target}")
        symlink_path.unlink()
        symlink_path.symlink_to(replacement_target)
    else:
        print(f"No suitable replacement target found for {symlink_path}")


def path_solve_contains_trajectory(path: Path, instance_id: str) -> bool:
    """
    Checks if the given path contains a trajectory with the specified trajectory_id.
    """
    for zip_path in path.rglob("solve-*.zip"):
        if zip_contains_trajectory(zip_path, instance_id):
            return True
    return False


def zip_contains_trajectory(zip_path: Path, instance_id: str) -> bool:
    """
    Checks if the given zip file contains a trajectory with the specified trajectory_id.
    """
    import zipfile

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        for file in zip_ref.namelist():
            if file.endswith(f"{instance_id}/navie/trajectory.jsonl"):
                return True
    return False


def main():
    test_patches_dir = Path("data/test_patches")
    for symlink_path in test_patches_dir.glob("*.json"):
        if symlink_path.is_symlink():
            rewrite_symlink(symlink_path)


if __name__ == "__main__":
    main()
