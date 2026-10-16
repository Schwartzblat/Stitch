import hashlib
import zipfile

import pytest

from conftest import build_module_apk
from stitch.dex_hash import apk_sha256, dex_sha256

FIXTURE_DEX_SHA256 = '5241b8649f3b1756ab0a32e13a29f534e9cd5298b004cf714d6e9a8f40a5e8fe'
DEX = {'classes.dex': b'dex\n035\x00one', 'classes2.dex': b'dex\n035\x00two', 'classes10.dex': b'dex\n035\x00ten'}


def _zip(path, entries, compress=zipfile.ZIP_DEFLATED):
    """Writes the entries in the given order."""
    with zipfile.ZipFile(path, 'w') as zip_file:
        for name, data in entries:
            zip_file.writestr(name, data, compress_type=compress)
    return path


def test_dex_hash_matches_fixture(tmp_path):
    # classes10 written first: order must come from the number, not the zip or the name
    apk = _zip(tmp_path / 'a.apk', [('classes10.dex', DEX['classes10.dex']), ('classes.dex', DEX['classes.dex']),
               ('assets/classes3.dex', b'not code'), ('classes.dex.bin', b'not code'), ('classes2.dex', DEX['classes2.dex'])])
    assert dex_sha256(apk) == FIXTURE_DEX_SHA256


def test_dex_hash_ignores_compression(tmp_path):
    entries = list(DEX.items())
    assert dex_sha256(_zip(tmp_path / 's.apk', entries, zipfile.ZIP_STORED)) == dex_sha256(_zip(tmp_path / 'd.apk', entries))


def test_dex_hash_of_bundle_uses_base_split(tmp_path):
    base = build_module_apk(tmp_path / 'base.apk', '', package='com.app', extra=DEX)
    split = build_module_apk(tmp_path / 'config.arm64_v8a.apk', '', package='com.app', split='config.arm64_v8a')
    bundle = _zip(tmp_path / 'app.apks', [('base.apk', base.read_bytes()), ('config.arm64_v8a.apk', split.read_bytes())])
    assert dex_sha256(bundle) == FIXTURE_DEX_SHA256


def test_dex_hash_without_dex_raises(tmp_path):
    with pytest.raises(ValueError):
        dex_sha256(_zip(tmp_path / 'n.apk', [('AndroidManifest.xml', b'x')]))


def test_apk_sha256_is_the_file_hash(tmp_path):
    apk = _zip(tmp_path / 'a.apk', list(DEX.items()))
    assert apk_sha256(apk) == hashlib.sha256(apk.read_bytes()).hexdigest()
