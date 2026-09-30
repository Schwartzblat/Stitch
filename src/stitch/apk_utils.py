import glob
import os
from pathlib import Path
import shutil
import subprocess
import typing
import zipfile
import yaml
from stitch.common import APKTOOL_PATH, FASTSIGNER_PATH, DEBUG_KEY_PATH, DEBUG_CERT_PATH, EXTRACTED_PATH, BUNDLE_APK_EXTRACTED_PATH, BUNDLE_DIR_PATH

main_apk_name = 'base.apk'

def is_bundle(path: os.PathLike) -> bool:
    """Only top-level .apk entries make a bundle: an XAPK keeps its splits at the root of the zip.

    An ordinary APK can carry .apk assets - Stitch's own output embeds its helpers as
    assets/stitch/*.apk - and matching those read it as a bundle, so re-patching a Stitch
    build went looking for a base.apk that isn't there.
    """
    with zipfile.ZipFile(path, 'r') as zip_file:
        return any(
            not info.is_dir() and '/' not in info.filename and info.filename.endswith('.apk')
            for info in zip_file.infolist()
        )


def extract_apk(apk_path: os.PathLike, temp_path: Path, extracted_path: typing.Optional[Path] = None) -> None:
    if str(apk_path).endswith('.xapk'):
        global main_apk_name
        with zipfile.ZipFile(apk_path, 'r') as zip_file:
            apk_files = [file for file in zip_file.namelist() if file.endswith('.apk')]
            if len(apk_files) == 0:
                raise ValueError('No APK files found in the XAPK.')
            main_apk_name = max(apk_files, key=lambda x: zip_file.getinfo(x).file_size)
    if is_bundle(apk_path):
        with zipfile.ZipFile(apk_path, 'r') as zip_file:
            zip_file.extractall(temp_path / BUNDLE_APK_EXTRACTED_PATH)
        os.makedirs(temp_path / BUNDLE_DIR_PATH, exist_ok=True)
        for apk_file in glob.iglob(str(temp_path / BUNDLE_APK_EXTRACTED_PATH / '*.apk')):
            if os.path.basename(apk_file) != main_apk_name:
                shutil.copy(apk_file, temp_path / BUNDLE_DIR_PATH)
        extract_apk(temp_path / BUNDLE_APK_EXTRACTED_PATH / main_apk_name, temp_path)
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
            extracted_path if extracted_path is not None else temp_path / EXTRACTED_PATH,
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
    for i in range(2):
        try:
            subprocess.check_call([
                "java",
                "-jar",
                APKTOOL_PATH,
                "build",
                "-q",
                str(input_path),
                "--output",
                str(output_path)
            ], timeout=20 * 60
            )
            break
        except Exception as e:
            if i == 1:
                raise e


def _key_args() -> typing.List[str]:
    keystore = os.environ.get('KEYSTORE_PATH')
    if keystore is None:
        return ["--key", str(DEBUG_KEY_PATH), "--cert", str(DEBUG_CERT_PATH)]
    args = ["--ks", keystore]
    if os.environ.get('KEY_ALIAS') is not None:
        args.extend(["--ks-key-alias", os.environ['KEY_ALIAS']])
    if os.environ.get('KEYSTORE_PASSWORD') is not None:
        args.extend(["--ks-pass", f"pass:{os.environ['KEYSTORE_PASSWORD']}"])
    if os.environ.get('KEY_PASSWORD') is not None:
        args.extend(["--key-pass", f"pass:{os.environ['KEY_PASSWORD']}"])
    return args


def _ensure_executable(path: os.PathLike) -> None:
    """Wheels built before the packaging fix installed fastsigner as 0644, so restore the bit in place."""
    mode = os.stat(path).st_mode
    if not mode & 0o111:
        os.chmod(path, mode | 0o111)


def sign_apk(bundle_dir: Path, apk_path: Path, output_path: Path, is_bundle_file: bool) -> None:
    _ensure_executable(FASTSIGNER_PATH)
    args = [str(FASTSIGNER_PATH), *_key_args()]
    if is_bundle_file:
        args.extend([str(apk_path), *glob.glob(str(bundle_dir / '*.apk'))])
    else:
        args.extend(["--out", str(output_path), str(apk_path)])
    subprocess.check_call(args, timeout=20 * 60)


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
