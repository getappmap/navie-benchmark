#!/usr/bin/env python

from argparse import ArgumentParser
from pathlib import Path
import re
from tarfile import TarFile
from zipfile import ZipFile


def main():
    parser = ArgumentParser(
        prog="unpack-appmaps", description="Unpack appmap files from solve runs"
    )
    parser.add_argument("solve_run", help="Path to the solve run directory", type=Path)
    parser.add_argument("output", help="Path to the output directory", type=Path)
    args = parser.parse_args()

    solve_run: Path = args.solve_run.resolve()
    output: Path = args.output.resolve()

    # Iterate through solve-*.zip files in the solve run directory
    for solve_file in solve_run.glob("solve-*.zip"):
        with ZipFile(solve_file) as solve_zip:
            # Look for <id>/navie/observe-test-patch/appmap.tar files in the archive
            for appmap_file in solve_zip.infolist():
                if appmap_file.filename.endswith("navie/observe-test-patch/appmap.tar"):
                    # make a directory for this id in the output
                    current_output = output / appmap_file.filename.split("/")[0]
                    current_output.mkdir(parents=True, exist_ok=True)
                    # extract the appmap.tar file to the output directory
                    appmap_tar_path = current_output / "appmap.tar"
                    appmap_file.filename = "appmap.tar"
                    solve_zip.extract(appmap_file, current_output)
                    # extract the tar, flattening the directories and printing full path
                    with TarFile(appmap_tar_path) as appmap_tar:
                        for ti in appmap_tar.getmembers():
                            if ti.isdir():
                                continue
                            ti.name = ti.name.split("/")[-1]
                            appmap_tar.extract(ti, current_output)
                            print(current_output / ti.name)

                    # remove the tar file
                    appmap_tar_path.unlink()


if __name__ == "__main__":
    main()
