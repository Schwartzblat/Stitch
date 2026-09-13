import io
import zipfile

from conftest import build_apk_zip
from stitch import module_resources


def _module(tmp_path, extra=None):
    entries = {
        'AndroidManifest.xml': b'binary-manifest',
        'resources.arsc': (b'arsc-table', zipfile.ZIP_STORED),
        'res/layout/activity_demo.xml': b'binary-layout',
        'classes.dex': b'dex',
        'lib/arm64-v8a/libyahfa.so': b'so',
        'assets/config.json': b'{}',
        'META-INF/CERT.SF': b'sig',
        'kotlin/kotlin.kotlin_builtins': b'kt',
    }
    entries.update(extra or {})
    return build_apk_zip(tmp_path / 'module.apk', entries)


def _names(data: bytes):
    return sorted(zipfile.ZipFile(io.BytesIO(data)).namelist())


def test_resource_only_apk_keeps_the_resource_table_and_res_tree(tmp_path):
    data = module_resources.build_resource_only_apk(_module(tmp_path))

    assert _names(data) == ['AndroidManifest.xml', 'res/layout/activity_demo.xml', 'resources.arsc']


def test_resource_only_apk_drops_code_libs_and_assets(tmp_path):
    """Shipping the dex and libs a second time would double the payload for nothing."""
    data = module_resources.build_resource_only_apk(_module(tmp_path))

    assert not any(n.startswith(('classes', 'lib/', 'assets/', 'META-INF/', 'kotlin/')) for n in _names(data))


def test_resource_table_stays_uncompressed(tmp_path):
    """Android mmaps resources.arsc; a deflated table fails to load on API 30+."""
    data = module_resources.build_resource_only_apk(_module(tmp_path))

    with zipfile.ZipFile(io.BytesIO(data)) as zip_file:
        assert zip_file.getinfo('resources.arsc').compress_type == zipfile.ZIP_STORED


def test_module_without_a_resource_table_produces_nothing(tmp_path):
    """Nothing to load at runtime, so injecting an empty APK would only add weight."""
    module = build_apk_zip(tmp_path / 'module.apk', {'AndroidManifest.xml': b'binary-manifest', 'classes.dex': b'dex'})

    assert module_resources.build_resource_only_apk(module) is None


def test_asset_path_is_named_after_the_module_package(tmp_path):
    """The runtime loader finds its own resources by its own package name."""
    assert module_resources.asset_path('com.smali_generator') == 'assets/stitch/com.smali_generator.apk'
