import json
import os
import shutil
from pathlib import Path

from .apk_utils import compile_apk, sign_apk
from .common import SMALI_EXTRACTED_PATH, SMALI_GENERATOR_TEMP_PATH, EXTRACTED_PATH
from . import apk_utils
from . import patcher

class Stitch:
    apk_path: Path
    output_apk: Path
    temp_path: Path
    artifactory: Path
    external_module: Path
    arch: str

    def __init__(self, apk_path: str, output_apk: str = 'out.apk', temp_path: str = './temp', artifactory: str = './artifactory.json', external_module: str = './smali_generator', arch: str = 'arm64-v8a'):
        self.apk_path = Path(apk_path)
        self.output_apk = Path(output_apk)
        self.temp_path = Path(temp_path)
        self.artifactory = Path(artifactory)
        self.external_module = Path(external_module)
        self.arch = arch
        os.makedirs(str(self.temp_path), exist_ok=True)

    def prepare_artifactory(self):
        if self.artifactory.exists():
            try:
                with open(self.artifactory, 'r') as file:
                    json.load(file)
            except json.decoder.JSONDecodeError:
                pass
            else:
                return
        else:
            with open(self.artifactory, 'w') as file:
                json.dump({'SOME_CONST_KEY': 'VALUE'}, file)


    def patch(self):
        apk_utils.extract_apk(self.apk_path, self.temp_path)

        self.prepare_artifactory()

        print('[+] Preparing the smali...')
        patcher.prepare_smali(self.temp_path, self.artifactory, self.external_module)

        print('[+] Applying the custom smali...')
        shutil.copytree(self.temp_path / SMALI_GENERATOR_TEMP_PATH / SMALI_EXTRACTED_PATH / 'smali',
                        self.temp_path / EXTRACTED_PATH / 'smali',
                        dirs_exist_ok=True)
        print('[+] Injecting the custom so...')
        os.makedirs(self.temp_path / EXTRACTED_PATH / 'lib' / self.arch, exist_ok=True)

        shutil.copytree(
            self.temp_path / SMALI_GENERATOR_TEMP_PATH / SMALI_EXTRACTED_PATH / 'lib' / self.arch,
            self.temp_path / EXTRACTED_PATH / 'lib' / self.arch,
            dirs_exist_ok=True)

        print('[+] Adding calls to the custom smali...')
        patcher.patch_entries(self.apk_path, self.temp_path)

        print('[+] Compiling APK...')
        compile_apk(self.temp_path / EXTRACTED_PATH, self.output_apk)

        print('[+] Signing APK...')
        sign_apk(self.apk_path, self.output_apk, Path('signed_' + str(self.output_apk)))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print('[+] Cleaning up...')
        self.clean_up()

    def clean_up(self):
        shutil.rmtree(self.temp_path, ignore_errors=True)
        self.artifactory.unlink(missing_ok=True)