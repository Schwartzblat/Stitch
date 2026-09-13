import io
import zipfile

from conftest import build_apk_zip, build_module_apk
from stitch import patcher

ARCH = 'arm64-v8a'


def test_module_assets_are_injected_into_the_target_apk(tmp_path):
    target = build_apk_zip(tmp_path / 'target.apk', {'classes.dex': b'host-dex', 'assets/host.txt': b'host'})
    module = build_apk_zip(tmp_path / 'module.apk', {'classes.dex': b'mod-dex', 'assets/config.json': b'{"k":1}'})

    patcher.inject_module_files(target, module, ARCH)

    with zipfile.ZipFile(target) as zip_file:
        assert zip_file.read('assets/config.json') == b'{"k":1}'


def test_module_asset_compression_is_preserved(tmp_path):
    """Some assets must stay uncompressed to be mmap'd at runtime; re-deflating them breaks that."""
    target = build_apk_zip(tmp_path / 'target.apk', {'classes.dex': b'host-dex'})
    module = build_apk_zip(tmp_path / 'module.apk', {
        'classes.dex': b'mod-dex',
        'assets/baseline.prof': (b'\x00' * 64, zipfile.ZIP_STORED),
        'assets/notes.txt': (b'y' * 64, zipfile.ZIP_DEFLATED),
    })

    patcher.inject_module_files(target, module, ARCH)

    with zipfile.ZipFile(target) as zip_file:
        assert zip_file.getinfo('assets/baseline.prof').compress_type == zipfile.ZIP_STORED
        assert zip_file.getinfo('assets/notes.txt').compress_type == zipfile.ZIP_DEFLATED


def test_module_asset_replaces_a_colliding_target_asset(tmp_path):
    target = build_apk_zip(tmp_path / 'target.apk', {'classes.dex': b'host-dex', 'assets/config.json': b'host-config'})
    module = build_apk_zip(tmp_path / 'module.apk', {'classes.dex': b'mod-dex', 'assets/config.json': b'module-config'})

    patcher.inject_module_files(target, module, ARCH)

    with zipfile.ZipFile(target) as zip_file:
        assert zip_file.namelist().count('assets/config.json') == 1
        assert zip_file.read('assets/config.json') == b'module-config'


def test_target_assets_the_module_does_not_touch_survive(tmp_path):
    target = build_apk_zip(tmp_path / 'target.apk', {
        'classes.dex': b'host-dex',
        'assets/font.ttf': (b'f' * 64, zipfile.ZIP_DEFLATED),
        'assets/dexopt/baseline.prof': (b'p' * 64, zipfile.ZIP_STORED),
    })
    module = build_apk_zip(tmp_path / 'module.apk', {'classes.dex': b'mod-dex', 'assets/config.json': b'{}'})

    patcher.inject_module_files(target, module, ARCH)

    with zipfile.ZipFile(target) as zip_file:
        assert zip_file.read('assets/font.ttf') == b'f' * 64
        assert zip_file.getinfo('assets/dexopt/baseline.prof').compress_type == zipfile.ZIP_STORED


def test_module_with_only_assets_still_injects(tmp_path):
    """The early-return guard must know about assets, or an assets-only module silently does nothing."""
    target = build_apk_zip(tmp_path / 'target.apk', {'classes.dex': b'host-dex'})
    module = build_apk_zip(tmp_path / 'module.apk', {'assets/config.json': b'{"k":1}'})

    patcher.inject_module_files(target, module, ARCH)

    with zipfile.ZipFile(target) as zip_file:
        assert zip_file.read('assets/config.json') == b'{"k":1}'


def test_replacing_a_target_asset_is_reported(tmp_path, capsys):
    """Silently clobbering a file in the app being patched is the failure mode worth surfacing."""
    target = build_apk_zip(tmp_path / 'target.apk', {'classes.dex': b'host-dex', 'assets/config.json': b'host-config'})
    module = build_apk_zip(tmp_path / 'module.apk', {'classes.dex': b'mod-dex', 'assets/config.json': b'module-config'})

    patcher.inject_module_files(target, module, ARCH)

    assert 'assets/config.json' in capsys.readouterr().out


def _module_with_resources(tmp_path, package='com.mod'):
    return build_module_apk(tmp_path / 'module.apk', '<application/>', package=package, extra={
        'classes.dex': b'mod-dex',
        'resources.arsc': (b'arsc-table', zipfile.ZIP_STORED),
        'res/layout/activity_demo.xml': b'binary-layout',
    })


def test_module_resource_apk_is_injected_as_an_asset(tmp_path):
    """The module's resource table has to reach the device somehow; it rides along as an asset."""
    target = build_apk_zip(tmp_path / 'target.apk', {'classes.dex': b'host-dex'})

    patcher.inject_module_files(target, _module_with_resources(tmp_path), ARCH)

    with zipfile.ZipFile(target) as zip_file:
        inner = zip_file.read('assets/stitch/com.mod.apk')
    with zipfile.ZipFile(io.BytesIO(inner)) as resource_apk:
        assert 'res/layout/activity_demo.xml' in resource_apk.namelist()
        assert resource_apk.read('resources.arsc') == b'arsc-table'


def test_no_resource_asset_when_the_module_has_no_resources(tmp_path):
    target = build_apk_zip(tmp_path / 'target.apk', {'classes.dex': b'host-dex'})
    module = build_module_apk(tmp_path / 'module.apk', '<application/>', extra={'classes.dex': b'mod-dex'})

    patcher.inject_module_files(target, module, ARCH)

    with zipfile.ZipFile(target) as zip_file:
        assert not any(n.startswith('assets/stitch/') for n in zip_file.namelist())


def test_resource_injection_can_be_turned_off(tmp_path):
    target = build_apk_zip(tmp_path / 'target.apk', {'classes.dex': b'host-dex'})

    patcher.inject_module_files(target, _module_with_resources(tmp_path), ARCH, inject_resources=False)

    with zipfile.ZipFile(target) as zip_file:
        assert not any(n.startswith('assets/stitch/') for n in zip_file.namelist())
