import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from stitch import apk_utils
from stitch.common import DEBUG_CERT_PATH, DEBUG_KEY_PATH

SAMPLE_APK = Path(__file__).parent.parent / '2048.apk'
KEYSTORE_ENV = ('KEYSTORE_PATH', 'KEY_ALIAS', 'KEYSTORE_PASSWORD', 'KEY_PASSWORD')

needs_build_tools = pytest.mark.skipif(
    shutil.which('apksigner') is None or shutil.which('zipalign') is None or not SAMPLE_APK.exists(),
    reason='needs apksigner, zipalign and 2048.apk',
)


@pytest.fixture(autouse=True)
def clean_keystore_env(monkeypatch):
    for name in KEYSTORE_ENV:
        monkeypatch.delenv(name, raising=False)


def test_debug_key_is_used_without_a_keystore():
    assert apk_utils._key_args() == ['--key', str(DEBUG_KEY_PATH), '--cert', str(DEBUG_CERT_PATH)]


def test_keystore_env_maps_to_fastsigner_flags(monkeypatch):
    monkeypatch.setenv('KEYSTORE_PATH', 'release.jks')
    monkeypatch.setenv('KEY_ALIAS', 'upload')
    monkeypatch.setenv('KEYSTORE_PASSWORD', 'store-pw')
    monkeypatch.setenv('KEY_PASSWORD', 'key-pw')

    assert apk_utils._key_args() == [
        '--ks', 'release.jks',
        '--ks-key-alias', 'upload',
        '--ks-pass', 'pass:store-pw',
        '--key-pass', 'pass:key-pw',
    ]


def _misaligned_copy(src: Path, dst: Path) -> Path:
    """Rewrite with plain zipfile, like patcher.inject_module_files does, so stored entries lose alignment."""
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, 'w') as zout:
        zout.writestr('!pad', b'x', compress_type=zipfile.ZIP_STORED)
        for item in zin.infolist():
            if not item.filename.startswith('META-INF/'):
                zout.writestr(item.filename, zin.read(item.filename), compress_type=item.compress_type)
    return dst


def _assert_signed_and_aligned(apk: Path) -> None:
    subprocess.run(['apksigner', 'verify', '--min-sdk-version', '24', str(apk)], check=True)
    subprocess.run(['zipalign', '-c', '-p', '4', str(apk)], check=True)


@needs_build_tools
def test_single_apk_is_signed_and_aligned_to_output(tmp_path):
    unsigned = _misaligned_copy(SAMPLE_APK, tmp_path / 'unsigned.apk')
    output = tmp_path / 'out.apk'

    apk_utils.sign_apk(tmp_path / 'missing_bundle', unsigned, output, is_bundle_file=False)

    _assert_signed_and_aligned(output)


@needs_build_tools
def test_bundle_apks_are_signed_in_place(tmp_path):
    bundle_dir = tmp_path / 'bundle'
    bundle_dir.mkdir()
    main = _misaligned_copy(SAMPLE_APK, tmp_path / 'unsigned.apk')
    split = _misaligned_copy(SAMPLE_APK, bundle_dir / 'split_config.apk')

    apk_utils.sign_apk(bundle_dir, main, tmp_path / 'unused.apk', is_bundle_file=True)

    for apk in (main, split):
        _assert_signed_and_aligned(apk)
    assert not (tmp_path / 'unused.apk').exists()
