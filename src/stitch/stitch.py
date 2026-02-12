import json
import os
import shutil
from pathlib import Path
from typing import List

from androguard.core.apk import APK
from stitch.apk_utils import is_bundle
from stitch.artifactory_generator.SimpleArtifactoryFinder import SimpleArtifactoryFinder
from stitch.common import BUNDLE_APK_EXTRACTED_PATH

from .apk_utils import compile_apk, sign_apk
from .artifactory_generator.generate_artifactory import generate_artifactory
from .common import SMALI_EXTRACTED_PATH, SMALI_GENERATOR_TEMP_PATH, EXTRACTED_PATH, ExternalModule
from . import apk_utils
from . import patcher


class Stitch:
    apk_path: Path
    output_apk: Path
    temp_path: Path
    artifactory: Path
    external_modules: List[ExternalModule]
    arch: str
    google_api_key: str
    should_sign: bool
    extra_artifacts: dict

    def __init__(self, apk_path: str, output_apk: str = 'out.apk', temp_path: str = './temp',
                 external_modules: List[ExternalModule] = None,
                 arch: str = 'arm64-v8a', artifactory_list: List[SimpleArtifactoryFinder] = None,
                 google_api_key: str = None, should_sign=True, extra_artifacts: dict = None):
        if external_modules is None:
            external_modules = [ExternalModule(
                Path('./smali_generator'),
                'invoke-static {}, Lcom/smali_generator/TheAmazingPatch;->on_load()V'
            )]
        self.apk_path = Path(apk_path)
        self.output_apk = Path(output_apk)
        self.temp_path = Path(temp_path)
        if self.temp_path.exists():
            raise Exception('[!] The temp path already exists')
        self.external_modules = external_modules
        self.arch = arch
        self.artifactory_list = [] if artifactory_list is None else artifactory_list
        os.makedirs(str(self.temp_path), exist_ok=True)
        self.google_api_key = google_api_key
        self.should_sign = should_sign
        if extra_artifacts is None:
            extra_artifacts = {}
        self.extra_artifacts = extra_artifacts

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

        artifactory = generate_artifactory(self.temp_path, self.artifactory_list)
        artifactory.update(self.extra_artifacts)

        smali_folders = [folder for folder in
                         (self.temp_path / EXTRACTED_PATH).iterdir() if
                         folder.is_dir() and (folder.name.startswith('smali_classes') or folder.name == 'smali')]
        new_smali_folders = [patcher.get_new_smali_folder(self.temp_path / EXTRACTED_PATH) for _ in
                             range(len(smali_folders))]
        print(f'[+] Applying the custom smali into {new_smali_folders[0].name}...')

        for i, folder in enumerate(smali_folders):
            # move every first folder within to the new smali folder
            for file in folder.iterdir():
                target_folder = new_smali_folders[i % len(new_smali_folders)]
                if not (target_folder / file.name).exists():
                    shutil.move(file, target_folder)
                    break
        target_smali_folder = patcher.get_new_smali_folder(self.temp_path / EXTRACTED_PATH)

        for module in self.external_modules:
            print('[+] Preparing the smali...')
            patcher.prepare_smali(self.temp_path, module.module_path, artifactory)

            shutil.copytree(self.temp_path / SMALI_GENERATOR_TEMP_PATH / SMALI_EXTRACTED_PATH / 'smali',
                            target_smali_folder,
                            dirs_exist_ok=True)
            print('[+] Injecting the custom so...')
            os.makedirs(self.temp_path / EXTRACTED_PATH / 'lib' / self.arch, exist_ok=True)

            shutil.copytree(
                self.temp_path / SMALI_GENERATOR_TEMP_PATH / SMALI_EXTRACTED_PATH / 'lib' / self.arch,
                self.temp_path / EXTRACTED_PATH / 'lib' / self.arch,
                dirs_exist_ok=True)
            shutil.rmtree(self.temp_path / SMALI_GENERATOR_TEMP_PATH, ignore_errors=True)

        invoke_lines = '\n\t'.join([module.invoke_line for module in self.external_modules])

        print('[+] Adding calls to the custom smali...')
        patcher.patch_entries(self.apk_path, self.temp_path, invoke_lines)

        if self.google_api_key is not None:
            print('[+] Patching google api key...')
            if is_bundle(self.apk_path):
                from stitch.apk_utils import main_apk_name
                package_name = APK(str(self.temp_path / BUNDLE_APK_EXTRACTED_PATH / main_apk_name)).get_package()
            else:
                package_name = APK(str(self.apk_path)).get_package()
            patcher.patch_google_api_key(self.temp_path, package_name, self.google_api_key)

        temp_output_apk = self.temp_path / 'unsigned.apk'

        print('[+] Compiling APK...')
        compile_apk(self.temp_path / EXTRACTED_PATH, temp_output_apk)

        if self.should_sign:
            print('[+] Signing APK...')
            sign_apk(self.temp_path, self.apk_path, temp_output_apk, self.output_apk)

        if is_bundle(self.apk_path):
            from stitch.apk_utils import main_apk_name
            shutil.move(temp_output_apk, self.temp_path / BUNDLE_APK_EXTRACTED_PATH / main_apk_name)
            shutil.move(self.temp_path / BUNDLE_APK_EXTRACTED_PATH, 'output_bundle_apks')
            temp_output_path = shutil.make_archive(str(self.temp_path / 'temp_output'), 'zip', 'output_bundle_apks')
            shutil.move(temp_output_path, self.output_apk)
            shutil.rmtree('output_bundle_apks', ignore_errors=True)
        else:
            if self.should_sign:
                shutil.move(temp_output_apk, self.output_apk)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print('[+] Cleaning up...')
        self.clean_up()

    def clean_up(self):
        shutil.rmtree(self.temp_path, ignore_errors=True)
