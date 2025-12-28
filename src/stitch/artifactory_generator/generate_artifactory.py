"""
This module supposed to be edited by the user to generate the artifactory for their project.
"""
import glob
import os
from pathlib import Path

from stitch.common import EXTRACTED_PATH


def generate_artifactory(temp_path: Path, artifacts_finders: list):
    artifacts = dict()
    for filename in glob.iglob(os.path.join(temp_path, EXTRACTED_PATH, "**", "*.smali"), recursive=True):
        if len(artifacts_finders) == 0:
            break
        with open(filename, "r", encoding="utf8") as f:
            data = f.read()
        for artifact_finder in artifacts_finders:
            if not artifact_finder.class_filter(data):
                continue
            artifact_finder.extract_artifacts(artifacts, data)
            if artifact_finder.is_once and artifact_finder.is_found:
                artifacts_finders.remove(artifact_finder)

    print(f'[+] Found artifacts:\n{artifacts}')
    return artifacts
