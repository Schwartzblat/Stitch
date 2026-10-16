"""Hashes that identify an app version: the code it runs and the file it ships as."""
import hashlib
import io
import os
import re
import typing
import zipfile

from stitch.apk_utils import base_apk_name, is_bundle

_CHUNK_SIZE = 1024 * 1024
_DEX_NAME = re.compile(r'classes(\d*)\.dex')


def _stream_sha256(stream: typing.BinaryIO) -> str:
    digest = hashlib.sha256()
    while chunk := stream.read(_CHUNK_SIZE):
        digest.update(chunk)
    return digest.hexdigest()


def _dex_digest(zip_file: zipfile.ZipFile) -> str:
    dex_entries = []
    for name in zip_file.namelist():
        match = _DEX_NAME.fullmatch(name)
        if match:
            # classes.dex is the first dex, classes2.dex the second
            dex_entries.append((int(match.group(1) or 1), name))
    if not dex_entries:
        raise ValueError('no classes*.dex entries to hash')

    digest = hashlib.sha256()
    for _, name in sorted(dex_entries):
        with zip_file.open(name) as entry:
            entry_hash = _stream_sha256(entry)
        digest.update(f'{name}\n{entry_hash}\n'.encode('utf-8'))
    return digest.hexdigest()


def dex_sha256(path: os.PathLike) -> str:
    """SHA-256 over the app's dex files, which is the same for every repackaging of one build.

    Each classes(N).dex entry, in numeric order, contributes name + "\\n" + sha256(uncompressed
    bytes) + "\\n", so compression, zip order and signing do not change it. For a split bundle
    it is the base split that is hashed. The phone reproduces this exactly.
    """
    if is_bundle(path):
        with zipfile.ZipFile(path, 'r') as bundle:
            with bundle.open(base_apk_name(path)) as base:
                base_bytes = io.BytesIO(base.read())
        with zipfile.ZipFile(base_bytes) as base_zip:
            return _dex_digest(base_zip)
    with zipfile.ZipFile(path, 'r') as zip_file:
        return _dex_digest(zip_file)


def apk_sha256(path: os.PathLike) -> str:
    """SHA-256 of the file itself, streamed."""
    with open(path, 'rb') as file:
        return _stream_sha256(file)
