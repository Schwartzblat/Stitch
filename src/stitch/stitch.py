import os
import shutil
from pathlib import Path
from typing import Optional

from . import apk_utils

class Stitch:
    apk_path: Path
    output_apk: Path
    temp_path: Path
    artifactory: Path

    def __init__(self, apk_path: str, output_apk: str = 'out.apk', temp_path: str = './temp', artifactory: str = './artifactory.json'):
        self.apk_path = Path(apk_path)
        self.output_apk = Path(output_apk)
        self.temp_path = Path(temp_path)
        self.artifactory = Path(artifactory)
        os.makedirs(str(self.temp_path), exist_ok=True)

    def prepare_artifactory(self):
        pass


    def patch(self):
        apk_utils.extract_apk(self.apk_path, self.temp_path)

        self.prepare_artifactory()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print('[+] Cleaning up...')
        self.clean_up()

    def clean_up(self):
        shutil.rmtree(self.temp_path, ignore_errors=True)
        if os.path.exists(self.artifactory):
            os.remove(self.artifactory)