import zipfile

from conftest import build_apk_zip
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
