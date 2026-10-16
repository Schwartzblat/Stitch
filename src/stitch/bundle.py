"""Patch bundles: our code for one app at one patcher version, signed so the phone can trust it."""
import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import lxml.etree
from androguard.core.apk import APK
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pyaxml import AXML

from stitch import patcher
from stitch.common import SMALI_GENERATOR_TEMP_PATH
from stitch.records import load_features

BUNDLE_FORMAT = 1
ANDROID_NS = 'http://schemas.android.com/apk/res/android'


class BundleError(Exception):
    pass


@dataclass
class BundleModule:
    name: str
    apk: Path


def build_manifest_additions(package: str, providers: List[str], module_apks: List[Path]) -> bytes:
    manifest = lxml.etree.fromstring(
        f'<manifest xmlns:android="{ANDROID_NS}" package="{package}"><application/></manifest>'
    )
    patcher._add_providers(manifest, providers)
    patcher._merge_module_manifests(manifest, module_apks)
    axml = AXML()
    axml.from_xml(manifest)
    axml.compute()
    return axml.pack()


def build_gradle_module(module_path: Path, work_dir: Path, substitutions: dict) -> Path:
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    built = patcher.prepare_smali(work_dir, Path(module_path), substitutions)
    result = work_dir / 'built.apk'
    shutil.copyfile(built, result)
    shutil.rmtree(work_dir / SMALI_GENERATOR_TEMP_PATH, ignore_errors=True)
    return result


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _min_sdk(apk: Path) -> int:
    value = APK(str(apk)).get_min_sdk_version()
    return int(value) if value else 1


def build_bundle(out_path: Path, package: str, patcher_version: str, modules: List[BundleModule],
                 providers: List[str], features_path: Path, signing_key_pem: Path,
                 min_store_version_code: int = 0) -> dict:
    load_features(features_path)
    key = serialization.load_pem_private_key(Path(signing_key_pem).read_bytes(), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise BundleError('the signing key must be an EC key')
    files: Dict[str, bytes] = {m.name: Path(m.apk).read_bytes() for m in modules}
    files['manifest-additions.xml'] = build_manifest_additions(package, providers, [m.apk for m in modules])
    files['features.json'] = Path(features_path).read_bytes()
    meta = {
        'format': BUNDLE_FORMAT,
        'package': package,
        'patcher_version': patcher_version,
        'min_sdk': max(_min_sdk(m.apk) for m in modules),
        'min_store_version_code': min_store_version_code,
        'dex_order': [m.name for m in modules],
        'files': {name: _sha256(data) for name, data in files.items()},
    }
    meta_bytes = json.dumps(meta, indent=2, sort_keys=True).encode()
    signature = key.sign(meta_bytes, ec.ECDSA(hashes.SHA256()))
    with zipfile.ZipFile(out_path, 'w') as zf:
        for name, data in files.items():
            method = zipfile.ZIP_STORED if name.endswith('.apk') else zipfile.ZIP_DEFLATED
            zf.writestr(name, data, compress_type=method)
        zf.writestr('bundle.json', meta_bytes, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr('bundle.sig', signature, compress_type=zipfile.ZIP_DEFLATED)
    return meta


def verify_bundle(path: Path, public_key_pem: bytes) -> dict:
    try:
        public_key = serialization.load_pem_public_key(public_key_pem)
        with zipfile.ZipFile(path) as zf:
            meta_bytes = zf.read('bundle.json')
            signature = zf.read('bundle.sig')
            public_key.verify(signature, meta_bytes, ec.ECDSA(hashes.SHA256()))
            meta = json.loads(meta_bytes)
            expected = set(meta['files'])
            actual = set(zf.namelist()) - {'bundle.json', 'bundle.sig'}
            if expected != actual:
                raise BundleError(f'bundle files differ from bundle.json: {sorted(expected ^ actual)}')
            for name, digest in meta['files'].items():
                if _sha256(zf.read(name)) != digest:
                    raise BundleError(f'hash mismatch for {name}')
    except BundleError:
        raise
    except InvalidSignature as error:
        raise BundleError('bad bundle signature') from error
    except (KeyError, ValueError, TypeError, zipfile.BadZipFile, OSError) as error:
        raise BundleError(f'unreadable bundle: {error}') from error
    return meta
