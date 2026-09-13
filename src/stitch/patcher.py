import glob
import os
from pathlib import Path
import re
import shutil
import subprocess
import zipfile
from typing import Optional, List, Tuple

import lxml.etree
from androguard.core.apk import APK
from androguard.util import set_log
from androguard.core.axml import ARSCParser
from pyaxml import AXML
from stitch import manifest_merger, module_resources
from stitch.apk_utils import find_smali_file_by_class_name
from stitch.common import ManifestKeys, SMALI_GENERATOR_TEMP_PATH, SMALI_GENERATOR_OUTPUT_PATH, \
    EXTRACTED_PATH

set_log('CRITICAL')
INVOKE_LINE = '\n\tinvoke-static {}, Lcom/smali_generator/TheAmazingPatch;->on_load()V\n\t'
ASSETS_PREFIX = 'assets/'


def patch_artifacts(artifactory: dict, smali_generator_temp_path: Path) -> None:
    for file in glob.iglob(str(smali_generator_temp_path / '**' / '**'), recursive=True, include_hidden=True):
        if os.path.isdir(file):
            continue
        with open(file, 'rb') as f:
            old_data = f.read()
        data = old_data
        for key, value in artifactory.items():
            data = data.replace(f'{{{{{key}}}}}'.encode(), value.encode())
        if data != old_data:
            with open(file, 'wb') as f:
                f.write(data)


def prepare_smali(temp_path: Path, external_module: Path, artifactory: dict) -> Path:
    smali_generator_temp_path = temp_path / SMALI_GENERATOR_TEMP_PATH
    print('[+] Copying the smali generator...')
    shutil.copytree(external_module, smali_generator_temp_path)
    print('[+] Patching the artifacts...')
    patch_artifacts(artifactory, smali_generator_temp_path)
    print('[+] Assembling the java...')
    subprocess.check_call(['./gradlew', 'assembleRelease'], cwd=smali_generator_temp_path)
    return smali_generator_temp_path / SMALI_GENERATOR_OUTPUT_PATH


def _dex_index(name: str) -> Optional[int]:
    m = re.fullmatch(r'classes(?:(\d+))?\.dex', name)
    if not m:
        return None
    return int(m.group(1)) if m.group(1) else 1


def _dex_name(index: int) -> str:
    return 'classes.dex' if index == 1 else f'classes{index}.dex'


def _resource_asset(generator_apk: Path) -> Optional[Tuple[str, bytes]]:
    """The module's resource table, packaged so it can be loaded at runtime from inside the patched APK."""
    data = module_resources.build_resource_only_apk(generator_apk)
    if data is None:
        return None
    package = manifest_merger.read_package(generator_apk)
    if not package:
        print('[-] Module manifest has no package attribute, skipping resource injection')
        return None
    return module_resources.asset_path(package), data


def inject_module_files(target_apk: Path, generator_apk: Path, arch: str, inject_resources: bool = True) -> None:
    with zipfile.ZipFile(generator_apk, 'r') as zin:
        gen_names = zin.namelist()
        gen_dex = sorted(
            (n for n in gen_names if _dex_index(n) is not None),
            key=lambda n: _dex_index(n) or 0,
        )
        gen_dex_data = [(n, zin.read(n)) for n in gen_dex]
        lib_prefix = f'lib/{arch}/'
        gen_libs = [(n, zin.read(n)) for n in gen_names if n.startswith(lib_prefix) and not n.endswith('/')]
        gen_assets = [(item.filename, zin.read(item.filename), item.compress_type) for item in zin.infolist()
                      if item.filename.startswith(ASSETS_PREFIX) and not item.is_dir()]
    if not gen_dex_data and not gen_libs and not gen_assets:
        print('[-] No dex, lib or asset files found in generator apk, skipping inject')
        return
    with zipfile.ZipFile(target_apk, 'r') as zin:
        target_names = zin.namelist()
        target_data = [(item, zin.read(item.filename)) for item in zin.infolist() if not item.is_dir()]
    max_dex = 0
    for name in target_names:
        idx = _dex_index(name)
        if idx is not None:
            max_dex = max(max_dex, idx)
    additions: dict = {}
    next_index = max_dex + 1
    for _, data in gen_dex_data:
        additions[_dex_name(next_index)] = (data, zipfile.ZIP_DEFLATED)
        next_index += 1
    for name, data in gen_libs:
        additions[name] = (data, zipfile.ZIP_STORED)
    for name, data, compress_type in gen_assets:
        if name in target_names:
            print(f'[-] Replacing {name} with the module\'s copy')
        additions[name] = (data, compress_type)
    resource_asset = _resource_asset(generator_apk) if inject_resources else None
    if resource_asset is not None:
        name, data = resource_asset
        print(f'[+] Injecting the module resource table as {name}...')
        additions[name] = (data, zipfile.ZIP_STORED)
    print(f'[+] Injecting {len(gen_dex_data)} dex file(s), {len(gen_libs)} lib file(s) and '
          f'{len(gen_assets)} asset file(s) into {target_apk.name}...')
    tmp_path = target_apk.with_suffix(target_apk.suffix + '.tmp')
    with zipfile.ZipFile(tmp_path, 'w') as zout:
        for item, data in target_data:
            if item.filename in additions:
                continue
            zout.writestr(item.filename, data, compress_type=item.compress_type)
        for name, (data, compress) in additions.items():
            zout.writestr(name, data, compress_type=compress)
    os.replace(tmp_path, target_apk)


def get_activities_with_entry_points(apk_path: Path) -> list:
    manifest: lxml.etree.Element = APK(str(apk_path)).get_android_manifest_xml()
    activities = []
    for element in manifest.find('.//application').getchildren():
        should_patch = False
        if element.tag == 'activity' or element.tag == 'activity-alias':
            should_patch = element.get(ManifestKeys.EXPORTED) == 'true'
        elif element.tag == 'provider' or element.tag == 'receiver' or element.tag == 'service':
            should_patch = True
        if should_patch:
            activities.append(element)
    return activities


def patch_or_add_function(smali_file_path: Path, function_name: str, invoke_line: str) -> None:
    with open(smali_file_path, 'r') as file:
        smali_file = file.read()
    matches = re.findall(fr'\.method \w+ [^\n]*{function_name}[^\n]*\n[^\n]+', smali_file)
    if len(matches) == 0:
        pass
    for match in matches:
        smali_file = smali_file.replace(match, f'{match}\n\t{invoke_line}\n\t')
    with open(smali_file_path, 'w') as file:
        file.write(smali_file)


def add_static_call_to_on_load(temp_path: Path, class_name: str, function_name: str, invoke_line: str) -> None:
    smali_file_path = find_smali_file_by_class_name(temp_path / EXTRACTED_PATH, class_name)
    if smali_file_path is None:
        print(f'[-] Failed to find smali file for {class_name}')
        return
    patch_or_add_function(smali_file_path, function_name, invoke_line)


def _provider_authority(host_package: Optional[str], provider_name: str) -> str:
    """Authorities are unique device-wide, so scope them to the app being patched."""
    if not host_package:
        print(f'[-] Host manifest has no package attribute, leaving {provider_name} as its own authority')
        return provider_name
    return f'{host_package}.{provider_name}'


def _add_providers(manifest: lxml.etree.Element, providers: List[str]) -> None:
    application = manifest_merger.find_application(manifest)
    host_package = manifest.get('package')
    for provider_name in providers:
        provider = lxml.etree.SubElement(application, 'provider')
        provider.set(ManifestKeys.NAME, provider_name)
        provider.set(ManifestKeys.EXPORTED, 'false')
        provider.set(ManifestKeys.AUTHORITIES, _provider_authority(host_package, provider_name))
        provider.set(ManifestKeys.INIT_ORDER, '2147483647')


def _merge_module_manifests(manifest: lxml.etree.Element, module_apks: List[Path]) -> None:
    for module_apk in module_apks:
        print(f'[+] Merging the manifest of {Path(module_apk).name}...')
        manifest_merger.merge_components(manifest, manifest_merger.collect_components(module_apk))


def patch_manifest(temp_path: Path, providers: List[str], module_apks: Optional[List[Path]] = None) -> None:
    manifest_path = temp_path / EXTRACTED_PATH / 'AndroidManifest.xml'
    raw = manifest_path.read_bytes()
    module_apks = [] if module_apks is None else module_apks
    try:
        axml, _ = AXML.from_axml(raw)
    except ValueError:
        parser = lxml.etree.XMLParser(remove_blank_text=False)
        tree = lxml.etree.parse(str(manifest_path), parser)
        manifest = tree.getroot()
        _add_providers(manifest, providers)
        _merge_module_manifests(manifest, module_apks)
        tree.write(str(manifest_path), encoding='utf-8', xml_declaration=True)
        return

    manifest = axml.to_xml()
    _add_providers(manifest, providers)
    _merge_module_manifests(manifest, module_apks)

    axml.from_xml(manifest)
    axml.compute()
    manifest_path.write_bytes(axml.pack())

def patch_google_api_key(temp_path: Path, package_name: str, custom_google_api_key: str) -> None:
    print('[+] Searching for google api key...')
    resources_path = temp_path / EXTRACTED_PATH / 'resources.arsc'
    resources = ARSCParser(resources_path.read_bytes())
    _, original_google_api_key = resources.get_string(package_name, 'google_api_key')
    print(f'[+] Original google api key: {original_google_api_key}')
    with open(resources_path, 'rb') as file:
        resources_data = file.read()
    resources_data = resources_data.replace(original_google_api_key.encode(), custom_google_api_key.encode())
    with open(resources_path, 'wb') as file:
        file.write(resources_data)


def get_new_smali_folder(smali_path: Path) -> Path:
    smali_folders = [folder for folder in smali_path.iterdir() if
                     folder.is_dir() and folder.name.startswith('smali_classes')]
    if not smali_folders:
        return smali_path / 'smali'
    smali_folders.sort(key=lambda x: int(x.name.replace('smali_classes', '')))
    smali_index = int(smali_folders[-1].name.replace('smali_classes', '')) + 1
    (smali_path / f'smali_classes{smali_index}').mkdir()
    return smali_path / f'smali_classes{smali_index}'

