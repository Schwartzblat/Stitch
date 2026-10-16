import os
import zipfile
from pathlib import Path

import pytest

from conftest import build_apk_zip, build_module_apk
from stitch import apk_utils


def _single_apk_with_embedded_helpers(path):
    """What Stitch itself produces: an ordinary APK carrying its helpers as assets/stitch/*.apk."""
    helper = build_apk_zip(path.parent / 'helper.apk', {'classes.dex': b'dex\n035\x00'}).read_bytes()
    return build_apk_zip(path, {
        'AndroidManifest.xml': b'manifest',
        'classes.dex': b'dex\n035\x00',
        'assets/stitch/com.paywall.apk': helper,
        'assets/stitch/com.smali_generator.apk': helper,
    })


def test_an_apk_embedding_apk_assets_is_not_a_bundle(tmp_path):
    assert not apk_utils.is_bundle(_single_apk_with_embedded_helpers(tmp_path / 'app.apk'))


def test_a_bundle_keeps_its_apks_at_the_root(tmp_path):
    bundle = build_apk_zip(tmp_path / 'app.xapk', {
        'manifest.json': b'{}',
        'base.apk': b'base',
        'config.arm64_v8a.apk': b'split',
    })

    assert apk_utils.is_bundle(bundle)


def test_an_already_stitched_apk_is_decoded_as_a_single_apk(tmp_path, monkeypatch):
    """Re-patching a Stitch output used to take the bundle branch and look for a base.apk that isn't there."""
    apk = _single_apk_with_embedded_helpers(tmp_path / 'app.apk')
    calls = []
    monkeypatch.setattr(apk_utils.subprocess, 'check_call', lambda args, **kwargs: calls.append(args))

    apk_utils.extract_apk(apk, tmp_path / 'work')

    (args,) = calls
    assert args[-1] == apk
    with zipfile.ZipFile(apk) as archive:
        assert 'assets/stitch/com.paywall.apk' in archive.namelist()


def _split_bytes(path, split=None, padding=0):
    """One split of a bundle: a real binary manifest, plus weight to make it the biggest."""
    extra = {}
    if split is None:
        extra['classes.dex'] = b'dex\n035\x00'
    if padding:
        extra['assets/pack.bin'] = (b'\0' * padding, zipfile.ZIP_STORED)
    return build_module_apk(path, '<application/>', package='com.example.game',
                            split=split, extra=extra).read_bytes()


def _bundle(tmp_path, splits, name='app.xapk', nested=None):
    """A bundle of (entry name, split name or None, padding) splits, stored so sizes are honest."""
    entries = {'manifest.json': b'{}'}
    for index, (entry, split, padding) in enumerate(splits):
        data = _split_bytes(tmp_path / f'split{index}.apk', split, padding)
        entries[entry] = (data, zipfile.ZIP_STORED)
    entries.update(nested or {})
    return build_apk_zip(tmp_path / name, entries)


def _entry_size(bundle, entry):
    with zipfile.ZipFile(bundle) as archive:
        return archive.getinfo(entry).file_size


def test_the_base_split_is_the_one_whose_manifest_declares_no_split_name(tmp_path):
    """A game whose assets ship as a split of their own makes the biggest APK the wrong one.

    Patching an asset split decompiles no classes, so every artifactory finder
    comes back empty and the module is built with its placeholders unsubstituted:
    an APK that installs, runs, and hooks nothing.
    """
    bundle = _bundle(tmp_path, [
        ('com.example.game.apk', None, 0),
        ('InstallPack.apk', 'InstallPack', 8192),
    ])

    assert _entry_size(bundle, 'InstallPack.apk') > _entry_size(bundle, 'com.example.game.apk')
    assert apk_utils.base_apk_name(bundle) == 'com.example.game.apk'


def test_a_bundle_whose_splits_all_declare_a_name_falls_back_to_the_biggest(tmp_path):
    """No split claims to be the base, so there is nothing better to go on than size."""
    bundle = _bundle(tmp_path, [
        ('config.arm64_v8a.apk', 'config.arm64_v8a', 0),
        ('config.xxhdpi.apk', 'config.xxhdpi', 8192),
    ])

    assert apk_utils.base_apk_name(bundle) == 'config.xxhdpi.apk'


def test_a_split_whose_manifest_cannot_be_read_does_not_hide_the_base(tmp_path):
    """Bundles carry odd .apk entries; one that cannot be parsed is simply not the base."""
    bundle = _bundle(tmp_path, [('com.example.game.apk', None, 0)], nested={
        'Android/obb/com.example.game.apk': (b'not a zip at all', zipfile.ZIP_STORED),
        'garbage.apk': (b'PK\x03\x04 truncated', zipfile.ZIP_STORED),
    })

    assert apk_utils.base_apk_name(bundle) == 'com.example.game.apk'


def test_an_apk_nested_inside_the_bundle_is_not_a_candidate(tmp_path):
    """is_bundle looks only at the root of the zip, and so must the choice of base."""
    helper = build_apk_zip(tmp_path / 'helper.apk', {
        'AndroidManifest.xml': b'manifest',
        'padding': (b'\0' * 16384, zipfile.ZIP_STORED),
    }).read_bytes()
    bundle = _bundle(tmp_path, [('com.example.game.apk', None, 0)], nested={
        'assets/stitch/com.smali_generator.apk': (helper, zipfile.ZIP_STORED),
    })

    assert apk_utils.base_apk_name(bundle) == 'com.example.game.apk'


def test_extract_apk_decodes_the_base_split_and_keeps_the_others_for_signing(tmp_path, monkeypatch):
    """The bundle branch must decode the split the base_apk_name picked, whatever the file is called."""
    bundle = _bundle(tmp_path, [
        ('com.example.game.apk', None, 0),
        ('InstallPack.apk', 'InstallPack', 8192),
    ], name='app.apkm')
    calls = []
    monkeypatch.setattr(apk_utils.subprocess, 'check_call', lambda args, **kwargs: calls.append(args))

    apk_utils.extract_apk(bundle, tmp_path / 'work')

    (args,) = calls
    assert Path(args[-1]).name == 'com.example.game.apk'
    assert os.listdir(tmp_path / 'work' / 'bundle_apks') == ['InstallPack.apk']


def test_an_xapk_with_no_apk_in_it_is_rejected(tmp_path):
    bundle = build_apk_zip(tmp_path / 'app.xapk', {'manifest.json': b'{}', 'icon.png': b'png'})

    with pytest.raises(ValueError):
        apk_utils.extract_apk(bundle, tmp_path / 'work')
