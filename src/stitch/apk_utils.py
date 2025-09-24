import glob
import os
from pathlib import Path
import shutil
import subprocess
import typing
import zipfile
from typing import Optional
import yaml
from .common import APKTOOL_PATH, UBER_APK_SIGNER_PATH, EXTRACTED_PATH, BUNDLE_APK_EXTRACTED_PATH


def is_bundle(path: os.PathLike) -> bool:
    with zipfile.ZipFile(path, 'r') as zip_file:
        for file in zip_file.namelist():
            if file.endswith('.apk'):
                return True
    return False


def extract_apk(apk_path: os.PathLike, temp_path: Path) -> None:
    if os.path.exists(temp_path / EXTRACTED_PATH):
        return
    if is_bundle(apk_path):
        with zipfile.ZipFile(apk_path, 'r') as zip_file:
            zip_file.extractall(temp_path / BUNDLE_APK_EXTRACTED_PATH)
        shutil.rmtree('./bundle_apks')
        os.makedirs('./bundle_apks', exist_ok=True)
        for apk_file in glob.iglob(str(temp_path / BUNDLE_APK_EXTRACTED_PATH / '*.apk')):
            if os.path.basename(apk_file) != 'base.apk':
                shutil.copy(apk_file, './bundle_apks')

        extract_apk(temp_path / BUNDLE_APK_EXTRACTED_PATH / 'base.apk', temp_path)
        return
    subprocess.check_call(
        [
            "java",
            "-jar",
            APKTOOL_PATH,
            "d",
            "-q",
            "-r",
            "--output",
            temp_path / EXTRACTED_PATH,
            apk_path,
        ],
        timeout=20 * 60,
    )


def compile_apk(input_path: Path, output_path: Path) -> None:
    yml_path = input_path / 'apktool.yml'
    if yml_path.exists():
        with open(yml_path, 'r') as file:
            apktool_yml = yaml.safe_load(file)
        if 'so' not in apktool_yml['doNotCompress']:
            apktool_yml['doNotCompress'].append('so')
        with open(yml_path, 'w') as file:
            yaml.safe_dump(apktool_yml, file, default_flow_style=False, sort_keys=False)
    subprocess.check_call([
        "java",
        "-jar",
        APKTOOL_PATH,
        "build",
        "-q",
        "--use-aapt2",
        str(input_path),
        "--output",
        str(output_path)
    ],
        timeout=20 * 60,

    )


def sign_apk(original_apk_path: Path, apk_path: Path, output_path: Path, bundle_apk_output: Optional[Path]) -> None:
    apk_files = [str(apk_path)]
    for file in glob.glob(str(bundle_apk_output / '*.apk')):
        apk_files.append(str(file))
    for file in apk_files:
        args = ["java", "-jar", UBER_APK_SIGNER_PATH]
        if os.environ.get('KEYSTORE_PATH') is not None:
            args.extend(["--ks", os.environ['KEYSTORE_PATH']])
        if os.environ.get('KEY_ALIAS') is not None:
            args.extend(["--ksAlias", os.environ['KEY_ALIAS']])
        if os.environ.get('KEYSTORE_PASSWORD') is not None:
            args.extend(["--ksPass", os.environ['KEYSTORE_PASSWORD']])
        if os.environ.get('KEY_PASSWORD') is not None:
            args.extend(["--ksKeyPass", os.environ['KEY_PASSWORD']])
        args.extend(['--allowResign', '--apks', file])
        subprocess.check_call(args, timeout=20 * 60)
        os.remove(file)
        if is_bundle(original_apk_path):
            os.rename(
                f'{file.removesuffix(".apk")}-aligned-signed.apk',
                f'{file.removesuffix(".apk")}.apk',
            )
        else:
            os.rename(f'{str(apk_path).removesuffix(".apk")}-aligned-signed.apk', output_path)


def _recursive_search_class(parent: Path, class_path: list) -> typing.Optional[Path]:
    for child in parent.iterdir():
        if len(class_path) == 1 and child.is_file() and child.name == f'{class_path[0]}.smali':
            return child
        elif child.is_dir() and child.name == class_path[0]:
            return _recursive_search_class(child, class_path[1:])
    return None


def find_smali_file_by_class_name(parent: Path, class_name: str) -> typing.Optional[Path]:
    for child in parent.iterdir():
        if not child.is_dir() or not str(child.name).startswith('smali'):
            continue
        file_path = _recursive_search_class(child, class_name.split('.'))
        if file_path:
            return file_path
    return None
