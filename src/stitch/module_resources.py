import io
import os
import typing
import zipfile

RESOURCE_TABLE_NAME = 'resources.arsc'
RESOURCE_ONLY_NAMES = ('AndroidManifest.xml', RESOURCE_TABLE_NAME)
RESOURCE_ONLY_PREFIXES = ('res/',)
ASSET_DIR = 'assets/stitch'


def asset_path(package: str) -> str:
    """Where the module's resource APK lives inside the patched APK."""
    return f'{ASSET_DIR}/{package}.apk'


def _belongs_in_resource_apk(name: str) -> bool:
    return name in RESOURCE_ONLY_NAMES or name.startswith(RESOURCE_ONLY_PREFIXES)


def build_resource_only_apk(module_apk: os.PathLike) -> typing.Optional[bytes]:
    """The module's resource table on its own, so it can be loaded at runtime without its code coming along."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(module_apk, 'r') as zin:
        if RESOURCE_TABLE_NAME not in zin.namelist():
            return None
        with zipfile.ZipFile(buffer, 'w') as zout:
            for item in zin.infolist():
                if item.is_dir() or not _belongs_in_resource_apk(item.filename):
                    continue
                zout.writestr(item.filename, zin.read(item.filename), compress_type=item.compress_type)
    return buffer.getvalue()
