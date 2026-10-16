import json

import pytest

from conftest import ANDROID_NS, build_apk_zip
from stitch.dex_hash import apk_sha256, dex_sha256
from stitch.records import Evaluation, Feature, Features, build_record, evaluate, load_features

FEATURES = Features(required_keys=['SIG'], official_cert_sha256=['ab'],
                    features=[Feature('pins', 'Pins', ['P1', 'P2']), Feature('ticks', 'Ticks', ['T1'])])


def test_all_present_is_supported_with_nothing_off():
    assert evaluate(FEATURES, {'SIG': 's', 'P1': 'a', 'P2': 'b', 'T1': 'c'}) == Evaluation([], [], True)


def test_missing_feature_key_turns_only_that_feature_off():
    assert evaluate(FEATURES, {'SIG': 's', 'P1': 'a', 'T1': 'c'}) == Evaluation(['P2'], ['pins'], True)


def test_missing_required_key_is_unsupported():
    assert evaluate(FEATURES, {'P1': 'a', 'P2': 'b', 'T1': 'c'}).supported is False


def test_empty_value_counts_as_missing():
    assert evaluate(FEATURES, {'SIG': 's', 'P1': '', 'P2': 'b', 'T1': 'c'}) == Evaluation(['P1'], ['pins'], True)


def _write(tmp_path, data):
    path = tmp_path / 'features.json'
    path.write_text(json.dumps(data))
    return path


def test_load_features(tmp_path):
    loaded = load_features(_write(tmp_path, {
        'required_keys': ['SIG'], 'official_cert_sha256': ['ab'],
        'features': [{'id': 'pins', 'title': 'Pins', 'keys': ['P1'], 'visible': False}, {'id': 'x', 'title': 'X', 'keys': []}]}))
    assert loaded.features == [Feature('pins', 'Pins', ['P1'], False), Feature('x', 'X', [], True)]
    assert loaded.all_keys() == {'SIG', 'P1'}


def test_load_features_rejects_duplicate_ids(tmp_path):
    path = _write(tmp_path, {'required_keys': ['SIG'], 'official_cert_sha256': [], 'features': [
        {'id': 'pins', 'title': 'A', 'keys': []}, {'id': 'pins', 'title': 'B', 'keys': []}]})
    with pytest.raises(ValueError):
        load_features(path)


def test_load_features_rejects_empty_required_keys(tmp_path):
    with pytest.raises(ValueError):
        load_features(_write(tmp_path, {'required_keys': [], 'official_cert_sha256': [], 'features': []}))


def test_build_record(tmp_path):
    from pyaxml import AXML
    axml = AXML()
    axml.from_xml(f'<manifest xmlns:android="{ANDROID_NS}" package="com.app" '
                  f'android:versionCode="42" android:versionName="1.2.3"/>')
    axml.compute()
    apk = build_apk_zip(tmp_path / 'app.apk', {'AndroidManifest.xml': axml.pack(), 'classes.dex': b'dex'})
    record = build_record(apk, {'SIG': 's', 'P1': 'a', 'P2': '', 'EXTRA': 'x'}, FEATURES, '3.0.0')
    assert set(record) == {'package', 'version_name', 'version_code', 'apk_sha256', 'dex_sha256', 'patcher_version',
                           'artifacts', 'missing_keys', 'features_off', 'supported'}
    assert record['package'] == 'com.app' and record['version_code'] == 42 and record['version_name'] == '1.2.3'
    assert record['artifacts'] == {'SIG': 's', 'P1': 'a'}
    assert record['missing_keys'] == ['P2', 'T1'] and record['features_off'] == ['pins', 'ticks']
    assert record['supported'] is True and record['patcher_version'] == '3.0.0'
    assert record['dex_sha256'] == dex_sha256(apk) and record['apk_sha256'] == apk_sha256(apk)
