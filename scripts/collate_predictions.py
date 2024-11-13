from collections.abc import Callable
import json
import shutil
from pathlib import Path
from typing import Optional
from zipfile import ZipFile

from tqdm import tqdm

from solver.load_instance_set import load_instance_set


def main(
    code_run_dir: str,
    target_dir: str,
    dry_run: bool = False,
    filter_set: Optional[str] = None,
    model_name="navie2+gpt4o+sonnet3.5",
):
    """
    Collates predictions and trajectories from a code run directory into a target directory.

    Args:
        code_run_dir: Path to the code run directory.
        target_dir: Path to the target directory.
        dry_run: Whether to perform a dry run.
        filter_set: The instance set to filter the instances by.
    """
    print(f"Using model name {model_name}")
    if filter_set:
        print(f"Filtering with instance set {filter_set}")
    code_run_p = Path(code_run_dir)
    target_p = Path(target_dir)

    include = make_filter(filter_set)

    # Create target directories
    target_p.mkdir(parents=True, exist_ok=True)
    (target_p / "trajs").mkdir(exist_ok=True)
    (target_p / "logs").mkdir(exist_ok=True)

    all_preds_file = target_p / "all_preds.jsonl"

    preds_count = 0
    traj_count = 0
    eval_count = 0

    # 1. Collate code patches
    code_patches_dir = code_run_p / "code_patches"
    if code_patches_dir.exists():
        with all_preds_file.open("a") as all_preds_f:
            for patch_file in tqdm(
                code_patches_dir.glob("*.json"), desc="Collating code patches"
            ):
                if dry_run and patch_file.name != "django__django-10880.json":
                    continue
                with patch_file.open() as f:
                    patch = json.load(f)
                instance_id = patch["instance_id"]
                if not include(instance_id):
                    continue
                preds_count += 1
                prediction = {
                    "instance_id": instance_id,
                    "model_name_or_path": model_name,
                    "model_patch": patch["code_patch"],
                }
                print(json.dumps(prediction), file=all_preds_f)

    # 2. Collate trajectories
    for solve_zip_file in tqdm(
        code_run_p.glob("solve-*.zip"), desc="Collating trajectories"
    ):
        if dry_run and solve_zip_file.name != "solve-0.zip":
            continue
        with ZipFile(solve_zip_file) as zf:
            for info in zf.infolist():
                if info.filename.endswith("/navie/trajectory.jsonl"):
                    instance_id = info.filename.split("/")[0]
                    if not include(instance_id):
                        continue
                    traj_count += 1
                    traj_target = target_p / "trajs" / f"{instance_id}.jsonl"
                    with traj_target.open("wb") as traj_target_f:

                        # 3a. Prepend test trajectory if available
                        test_patch_symlink = (
                            Path.cwd() / "data" / "test_patches" / f"{instance_id}.json"
                        )
                        if test_patch_symlink.exists():
                            test_patch_path = test_patch_symlink.resolve()
                            test_run_dir = test_patch_path.parent.parent
                            test_traj_zip_files = list(test_run_dir.glob("solve-*.zip"))
                            for test_traj_zip_file in test_traj_zip_files:
                                with ZipFile(test_traj_zip_file) as test_zf:
                                    for testinfo in test_zf.infolist():
                                        if testinfo.filename.endswith(
                                            f"{instance_id}/navie/trajectory.jsonl"
                                        ):
                                            traj_target = (
                                                target_p
                                                / "trajs"
                                                / f"{instance_id}.jsonl"
                                            )
                                            with test_zf.open(testinfo) as test_traj_f:
                                                shutil.copyfileobj(
                                                    test_traj_f, traj_target_f
                                                )
                                            break
                                    else:
                                        continue
                                    break
                            else:
                                print(
                                    f"Could not find test trajectory for {instance_id} in {test_run_dir}"
                                )
                        with zf.open(info) as code_traj_f:
                            shutil.copyfileobj(code_traj_f, traj_target_f)

    eval_seen = set()

    # 4. Unpack run evaluation logs
    for eval_zip_file in tqdm(
        code_run_p.glob("run_evaluation-*.zip"), desc="Unpacking evaluation logs"
    ):
        if dry_run and eval_zip_file.name != "run_evaluation-0.zip":
            continue
        with ZipFile(eval_zip_file) as zf:
            # extract everything discarding leading paths,
            # eg. verified_33_pct_1/navie_082024+claude-3-5-sonnet-20241022/astropy__astropy-12907/foo.txt
            # to target_dir/logs/astropy__astropy-12907/foo.txt
            for info in zf.infolist():
                # skip paths containing "image_build_dir"
                if "image_build_dir" in info.filename:
                    continue

                [instance_id, file_name] = info.filename.split("/")[-2:]
                if not include(instance_id):
                    continue

                if instance_id not in eval_seen:
                    eval_count += 1
                    eval_seen.add(instance_id)

                target_path = target_p / "logs" / instance_id / file_name
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with target_path.open("wb") as f:
                    shutil.copyfileobj(zf.open(info), f)

    print(f"Total predictions: {preds_count}")
    print(f"Total trajectories: {traj_count}")
    print(f"Total evaluations: {eval_count}")


def make_filter(instance_set: Optional[str]) -> Callable[[str], bool]:
    if instance_set:
        ids = load_instance_set(instance_set)
        return lambda x: x in ids
    else:
        return lambda x: True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("code_run_dir", type=str)
    parser.add_argument("target_dir", type=str)
    parser.add_argument("--dry_run", action="store_true")
    parser.add_argument("--filter_set", type=str)
    args = parser.parse_args()

    main(args.code_run_dir, args.target_dir, args.dry_run, args.filter_set)
