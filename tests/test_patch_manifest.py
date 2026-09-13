import lxml.etree

from conftest import android, build_module_apk, read_binary_manifest, write_binary_manifest
from stitch import patcher
from stitch.common import EXTRACTED_PATH


def _host(tmp_path, inner: str = '<application><activity android:name="com.host.Main"/></application>'):
    extracted = tmp_path / EXTRACTED_PATH
    extracted.mkdir()
    write_binary_manifest(extracted / 'AndroidManifest.xml', inner)
    return extracted / 'AndroidManifest.xml'


def _module(tmp_path):
    return build_module_apk(
        tmp_path / 'module.apk',
        '<application><activity android:name=".Settings" android:exported="false"/></application>',
    )


def test_module_activity_reaches_the_patched_binary_manifest(tmp_path):
    manifest_path = _host(tmp_path)

    patcher.patch_manifest(tmp_path, ['com.mod.InitProvider'], [_module(tmp_path)])

    application = read_binary_manifest(manifest_path).find('application')
    assert 'com.mod.Settings' in [element.get(android('name')) for element in application]


def test_provider_injection_still_happens_when_a_module_apk_is_merged(tmp_path):
    manifest_path = _host(tmp_path)

    patcher.patch_manifest(tmp_path, ['com.mod.InitProvider'], [_module(tmp_path)])

    providers = read_binary_manifest(manifest_path).find('application').findall('provider')
    assert [element.get(android('name')) for element in providers] == ['com.mod.InitProvider']


def test_module_activity_reaches_a_plain_xml_manifest(tmp_path):
    """apktool leaves a decoded manifest as text; that branch must merge too."""
    extracted = tmp_path / EXTRACTED_PATH
    extracted.mkdir()
    manifest_path = extracted / 'AndroidManifest.xml'
    manifest_path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.host">'
        '<application><activity android:name="com.host.Main"/></application></manifest>'
    )

    patcher.patch_manifest(tmp_path, ['com.mod.InitProvider'], [_module(tmp_path)])

    merged = lxml.etree.parse(str(manifest_path)).getroot().find('application')
    assert 'com.mod.Settings' in [element.get(android('name')) for element in merged]


def test_provider_authority_is_scoped_to_the_host_package(tmp_path):
    """Authorities are unique device-wide: two apps patched with the same module must not collide."""
    manifest_path = _host(tmp_path)

    patcher.patch_manifest(tmp_path, ['com.mod.InitProvider'], [_module(tmp_path)])

    provider = read_binary_manifest(manifest_path).find('application').find('provider')
    assert provider.get(android('authorities')) == 'com.host.com.mod.InitProvider'


def test_provider_authority_falls_back_to_the_class_name_without_a_host_package(tmp_path):
    extracted = tmp_path / EXTRACTED_PATH
    extracted.mkdir()
    manifest_path = extracted / 'AndroidManifest.xml'
    manifest_path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<manifest xmlns:android="http://schemas.android.com/apk/res/android">'
        '<application/></manifest>'
    )

    patcher.patch_manifest(tmp_path, ['com.mod.InitProvider'])

    provider = lxml.etree.parse(str(manifest_path)).getroot().find('application').find('provider')
    assert provider.get(android('authorities')) == 'com.mod.InitProvider'
