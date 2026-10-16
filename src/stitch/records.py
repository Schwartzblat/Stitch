"""Version records: what the finders found for one app version, and what that leaves working."""
import dataclasses
import json
import os
import typing
import zipfile

from androguard.core.apk import APK

from stitch.apk_utils import base_apk_name, is_bundle
from stitch.dex_hash import apk_sha256, dex_sha256


@dataclasses.dataclass
class Feature:
    id: str
    title: str
    keys: typing.List[str]
    visible: bool = True


@dataclasses.dataclass
class Features:
    required_keys: typing.List[str]
    official_cert_sha256: typing.List[str]
    features: typing.List[Feature]

    def all_keys(self) -> typing.Set[str]:
        keys = set(self.required_keys)
        for feature in self.features:
            keys.update(feature.keys)
        return keys


@dataclasses.dataclass
class Evaluation:
    missing_keys: typing.List[str]
    features_off: typing.List[str]
    supported: bool


def load_features(path: os.PathLike) -> Features:
    with open(path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    required_keys = list(data.get('required_keys') or [])
    if not required_keys:
        raise ValueError('features.json needs at least one required key')
    features = [Feature(item['id'], item['title'], list(item.get('keys', [])), item.get('visible', True))
                for item in data.get('features', [])]
    ids = [feature.id for feature in features]
    duplicates = sorted({feature_id for feature_id in ids if ids.count(feature_id) > 1})
    if duplicates:
        raise ValueError(f'duplicate feature ids in features.json: {duplicates}')
    return Features(required_keys, list(data.get('official_cert_sha256', [])), features)


def evaluate(features: Features, artifacts: dict) -> Evaluation:
    """An empty value counts as missing. A missing feature key turns that feature off; a missing required one
    makes the version unsupported."""
    def present(key: str) -> bool:
        return bool(artifacts.get(key))

    missing = {key for key in features.all_keys() if not present(key)}
    features_off = [feature.id for feature in features.features if any(key in missing for key in feature.keys)]
    return Evaluation(sorted(missing), features_off, all(present(key) for key in features.required_keys))


def _read_apk(apk_path: os.PathLike) -> APK:
    if is_bundle(apk_path):
        with zipfile.ZipFile(apk_path, 'r') as bundle:
            return APK(bundle.read(base_apk_name(apk_path)), raw=True)
    return APK(str(apk_path))


def build_record(apk_path: os.PathLike, artifacts: dict, features: Features, patcher_version: str) -> dict:
    apk = _read_apk(apk_path)
    kept = {key: value for key, value in artifacts.items() if key in features.all_keys() and value}
    evaluation = evaluate(features, kept)
    return {
        'package': apk.get_package(),
        'version_name': apk.get_androidversion_name(),
        'version_code': int(apk.get_androidversion_code()),
        'apk_sha256': apk_sha256(apk_path),
        'dex_sha256': dex_sha256(apk_path),
        'patcher_version': patcher_version,
        'artifacts': kept,
        'missing_keys': evaluation.missing_keys,
        'features_off': evaluation.features_off,
        'supported': evaluation.supported,
    }
