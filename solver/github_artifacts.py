import urllib.request
from http.client import HTTPMessage
from pathlib import Path
from typing import Tuple

import github
import github.WorkflowRun


def download_artifacts(target_dir: Path, run: github.WorkflowRun.WorkflowRun):
    for artifact in run.get_artifacts():
        print(f"Importing artifact {artifact.id} from run {run.id}")
        download_url = artifact.archive_download_url
        target_file = target_dir / f"{artifact.name}.zip"
        status, headers, _ = run._requester.requestJson("GET", download_url)
        if status == 302:
            result: Tuple[str, HTTPMessage] = urllib.request.urlretrieve(
                headers["location"], target_file
            )
        else:
            result: Tuple[str, HTTPMessage] = urllib.request.urlretrieve(
                download_url, target_file
            )

        print(f"  {result[0]} ({result[1].get('Content-Length')} bytes)")
