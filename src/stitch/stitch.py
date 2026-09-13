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
from .common import SMALI_GENERATOR_TEMP_PATH, EXTRACTED_PATH, ExternalModule
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
    merge_module_manifests: bool
    inject_module_resources: bool

    def __init__(self, apk_path: str, output_apk: str = 'out.apk', temp_path: str = './temp',
                 external_modules: List[ExternalModule] = None,
                 arch: str = 'arm64-v8a', artifactory_list: List[SimpleArtifactoryFinder] = None,
                 google_api_key: str = None, should_sign=True, extra_artifacts: dict = None,
                 merge_module_manifests: bool = True, inject_module_resources: bool = True):
        if external_modules is None:
            external_modules = [ExternalModule(
                Path('./smali_generator'),
                'com.smali_generator.InitProvider'
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
        self.merge_module_manifests = merge_module_manifests
        self.inject_module_resources = inject_module_resources
        self.is_bundle_file = is_bundle(self.apk_path)

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

        generator_apks = []
        for i, module in enumerate(self.external_modules):
            print('[+] Preparing the smali...')
            built_apk = patcher.prepare_smali(self.temp_path, module.module_path, artifactory)
            saved_apk = self.temp_path / f'generator-{i}.apk'
            shutil.copy(built_apk, saved_apk)
            generator_apks.append(saved_apk)
            shutil.rmtree(self.temp_path / SMALI_GENERATOR_TEMP_PATH, ignore_errors=True)

        print('[+] Patching the manifest...')
        patcher.patch_manifest(
            self.temp_path,
            [module.invoke_line for module in self.external_modules],
            generator_apks if self.merge_module_manifests else [],
        )

        if self.google_api_key is not None:
            print('[+] Patching google api key...')
            if self.is_bundle_file:
                from stitch.apk_utils import main_apk_name
                package_name = APK(str(self.temp_path / BUNDLE_APK_EXTRACTED_PATH / main_apk_name)).get_package()
            else:
                package_name = APK(str(self.apk_path)).get_package()
            patcher.patch_google_api_key(self.temp_path, package_name, self.google_api_key)

        temp_output_apk = self.temp_path / 'unsigned.apk'

        print('[+] Compiling APK...')
        compile_apk(self.temp_path / EXTRACTED_PATH, temp_output_apk)

        print('[+] Injecting module files...')
        for generator_apk in generator_apks:
            patcher.inject_module_files(temp_output_apk, generator_apk, self.arch,
                                        inject_resources=self.inject_module_resources)

        if self.should_sign:
            print('[+] Signing APK...')
            sign_apk(self.temp_path / BUNDLE_APK_EXTRACTED_PATH, temp_output_apk, self.output_apk, self.is_bundle_file)

        if self.is_bundle_file:
            from stitch.apk_utils import main_apk_name
            shutil.move(temp_output_apk, self.temp_path / BUNDLE_APK_EXTRACTED_PATH / main_apk_name)
            shutil.move(self.temp_path / BUNDLE_APK_EXTRACTED_PATH, 'output_bundle_apks')
            temp_output_path = shutil.make_archive(str(self.temp_path / 'temp_output'), 'zip', 'output_bundle_apks')
            shutil.move(temp_output_path, self.output_apk)
            shutil.rmtree('output_bundle_apks', ignore_errors=True)
        else:
            if not self.should_sign:
                shutil.move(temp_output_apk, self.output_apk)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print('[+] Cleaning up...')
        self.clean_up()

    def clean_up(self):
        shutil.rmtree(self.temp_path, ignore_errors=True)
