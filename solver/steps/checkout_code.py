from os import chdir, getcwd, unlink
import subprocess
import tarfile
from swebench.harness.docker_utils import exec_run_with_timeout


def checkout_code(log, container, source_dir, tmp_dir):
    # source_dir should not exist
    if source_dir.exists():
        raise ValueError(f"{source_dir} already exists")

    source_dir.mkdir(parents=True, exist_ok=True)

    # Export the .git directory from the container as a tar file
    # Unpack it into the work directory
    log("checkout-code", "Creating git archive in the container")
    exec_run_with_timeout(
        container, "git archive --format=tar.gz -o /tmp/source.tar.gz HEAD"
    )
    log(
        "checkout-code",
        f"Copying git archive out of the container and unpacking it to {source_dir}",
    )

    (archive, _) = container.get_archive("/tmp/source.tar.gz")
    with open(tmp_dir / "source.tar", "wb") as f:
        for chunk in archive:
            f.write(chunk)

    # Unpack the tar file to the temp directory
    with tarfile.open(tmp_dir / "source.tar") as tar:
        tar.extractall(tmp_dir)
    # Unpack the source.tar.gz to the source directory
    with tarfile.open(tmp_dir / "source.tar.gz") as tar:
        tar.extractall(source_dir)

    # Delete the files in tmp dir
    for file in ["source.tar", "source.tar.gz"]:
        unlink(tmp_dir / file)

    # chdir to the source directory.
    pwd = getcwd()
    chdir(source_dir)
    try:
        # Initialize git and add all files; on this filesystem, not in the container.
        subprocess.run(["git", "init"], check=True)
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", f"Baseline commit"], check=True)
    finally:
        chdir(pwd)
