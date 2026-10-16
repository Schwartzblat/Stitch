import json
import zipfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pyaxml import AXML

from conftest import android, build_module_apk
from stitch.bundle import BundleError, BundleModule, build_bundle, build_manifest_additions, verify_bundle

VALID_FEATURES_JSON = json.dumps({
    'required_keys': ['a'],
    'official_cert_sha256': [],
    'features': [{'id': 'f', 'title': 'F', 'keys': ['a']}],
})


def _decode(data: bytes):
    axml, _ = AXML.from_axml(data)
    return axml.to_xml()


def _ec_keypair(tmp_path, name='key.pem'):
    key = ec.generate_private_key(ec.SECP256R1())
    path = tmp_path / name
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    public = key.public_key().public_bytes(serialization.Encoding.PEM,
                                           serialization.PublicFormat.SubjectPublicKeyInfo)
    return path, public


def _modules(tmp_path):
    hook = build_module_apk(tmp_path / 'hook.apk',
        '<uses-sdk android:minSdkVersion="33"/><uses-permission android:name="android.permission.INTERNET"/>'
        '<application><activity android:name="com.smali_generator.ui.PatchSettingsActivity" android:exported="false"/></application>',
        package='com.smali_generator')
    pay = build_module_apk(tmp_path / 'pay.apk',
        '<uses-sdk android:minSdkVersion="30"/><uses-permission android:name="android.permission.INTERNET"/><application/>',
        package='com.paywall')
    return hook, pay


def _bundle(tmp_path, name='b.zip'):
    key_pem, pub_pem = _ec_keypair(tmp_path)
    hook, pay = _modules(tmp_path)
    features = tmp_path / 'features.json'
    features.write_text(VALID_FEATURES_JSON)
    out = tmp_path / name
    meta = build_bundle(out, 'com.whatsapp', '3.0.0',
                        [BundleModule('module.apk', hook), BundleModule('paywall.apk', pay)],
                        ['com.smali_generator.InitProvider'], features, key_pem, min_store_version_code=7)
    return out, meta, pub_pem


def test_additions_hold_providers_and_components(tmp_path):
    hook, pay = _modules(tmp_path)
    xml = _decode(build_manifest_additions('com.whatsapp', ['com.smali_generator.InitProvider'], [hook, pay]))
    provider = xml.find('application/provider')
    assert provider.get(android('authorities')) == 'com.whatsapp.com.smali_generator.InitProvider'
    assert provider.get(android('exported')) == 'false' and provider.get(android('initOrder')) == '2147483647'
    assert xml.find('application/activity').get(android('name')) == 'com.smali_generator.ui.PatchSettingsActivity'


def test_additions_merge_duplicate_permissions_once(tmp_path):
    hook, pay = _modules(tmp_path)
    xml = _decode(build_manifest_additions('com.whatsapp', [], [hook, pay]))
    assert len(xml.findall('uses-permission')) == 1


def test_bundle_round_trip(tmp_path):
    out, meta, pub_pem = _bundle(tmp_path)
    assert verify_bundle(out, pub_pem) == meta
    assert meta['format'] == 1 and meta['min_sdk'] == 33 and meta['min_store_version_code'] == 7
    assert meta['dex_order'] == ['module.apk', 'paywall.apk']
    assert set(meta['files']) == {'module.apk', 'paywall.apk', 'manifest-additions.xml', 'features.json'}
    assert set(zipfile.ZipFile(out).namelist()) == set(meta['files']) | {'bundle.json', 'bundle.sig'}
    infos = {i.filename: i.compress_type for i in zipfile.ZipFile(out).infolist()}
    assert infos['module.apk'] == zipfile.ZIP_STORED and infos['features.json'] == zipfile.ZIP_DEFLATED


def test_tampered_file_fails_verification(tmp_path):
    out, _, pub_pem = _bundle(tmp_path)
    tampered = tmp_path / 't.zip'
    with zipfile.ZipFile(out) as zin, zipfile.ZipFile(tampered, 'w') as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == 'features.json':
                data = b'{}'
            zout.writestr(item, data)
    with pytest.raises(BundleError):
        verify_bundle(tampered, pub_pem)


def test_wrong_key_fails_verification(tmp_path):
    out, _, _ = _bundle(tmp_path)
    _, other_pub = _ec_keypair(tmp_path, 'other.pem')
    with pytest.raises(BundleError):
        verify_bundle(out, other_pub)


def test_invalid_features_rejected(tmp_path):
    key_pem, _ = _ec_keypair(tmp_path)
    hook, _ = _modules(tmp_path)
    features = tmp_path / 'features.json'
    features.write_text('{"required_keys": []}')
    with pytest.raises(ValueError):
        build_bundle(tmp_path / 'b.zip', 'p', '1', [BundleModule('module.apk', hook)], [], features, key_pem)
