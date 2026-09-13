import copy
import dataclasses
import os
import re
import typing
import zipfile

import lxml.etree
from pyaxml import AXML

from stitch.common import ANDROID_MANIFEST_RELEVANT_TAGS, ANDROID_MANIFEST_ROOT_TAGS, ManifestKeys

RELATIVE_NAME_KEYS = (ManifestKeys.NAME, ManifestKeys.TARGET_ACTIVITY)
TOOLS_NAMESPACE = '{http://schemas.android.com/tools}'
FRAMEWORK_PACKAGE_ID = 0x01
RESOURCE_REFERENCE_RE = re.compile(r'^[@?]([0-9a-fA-F]{1,8})$')


@dataclasses.dataclass
class ModuleComponents:
    application: typing.List[lxml.etree.Element]
    root: typing.List[lxml.etree.Element]


def _strip_tools_attributes(element: lxml.etree.Element) -> None:
    """`tools:` attributes only steer the Gradle manifest merger and the host manifest has no tools namespace."""
    for node in element.iter():
        if not isinstance(node.tag, str):
            continue
        for key in [key for key in node.attrib if key.startswith(TOOLS_NAMESPACE)]:
            del node.attrib[key]


def _is_module_resource_reference(value: str) -> bool:
    """A reference into the module's own resource table, which is never injected into the host APK."""
    match = RESOURCE_REFERENCE_RE.match(value)
    if match is None:
        return False
    return (int(match.group(1), 16) >> 24) != FRAMEWORK_PACKAGE_ID


def _drop_module_resource_references(element: lxml.etree.Element) -> None:
    for node in element.iter():
        if not isinstance(node.tag, str):
            continue
        for key, value in list(node.attrib.items()):
            if _is_module_resource_reference(value):
                print(f'[-] Dropping {key.split("}")[-1]}="{value}" from <{node.tag}>: '
                      f'module resources are not injected into the host APK')
                del node.attrib[key]


def _require_explicit_exported(element: lxml.etree.Element) -> None:
    """Android 12+ refuses to install a component that has an intent filter but no explicit android:exported."""
    if element.find('intent-filter') is None or element.get(ManifestKeys.EXPORTED) is not None:
        return
    raise ValueError(
        f'<{element.tag}> {element.get(ManifestKeys.NAME)} has an intent-filter but no android:exported. '
        f'Declare android:exported in the module manifest; Stitch will not guess it.'
    )


def _resolve_relative_names(element: lxml.etree.Element, package: str) -> None:
    """Expand the `.Foo` shorthand, which is relative to the module package and meaningless in the host manifest."""
    for key in RELATIVE_NAME_KEYS:
        value = element.get(key)
        if value is None or not value.startswith('.'):
            continue
        if not package:
            raise ValueError(
                f'<{element.tag}> declares the relative name "{value}" but the module manifest has no package '
                f'attribute, so it cannot be resolved. Use a fully qualified class name.'
            )
        element.set(key, f'{package}{value}')


def _prepare(element: lxml.etree.Element, package: str) -> lxml.etree.Element:
    element = copy.deepcopy(element)
    _strip_tools_attributes(element)
    _resolve_relative_names(element, package)
    _require_explicit_exported(element)
    _drop_module_resource_references(element)
    return element


def extract_components(module_manifest: lxml.etree.Element, package: str) -> ModuleComponents:
    application = module_manifest.find('application')
    children = [] if application is None else list(application)
    return ModuleComponents(
        application=[_prepare(child, package) for child in children
                     if child.tag in ANDROID_MANIFEST_RELEVANT_TAGS],
        root=[_prepare(child, package) for child in module_manifest
              if child.tag in ANDROID_MANIFEST_ROOT_TAGS],
    )


def read_manifest(module_apk: os.PathLike) -> lxml.etree.Element:
    """The manifest of an AGP-built module APK, as an lxml tree."""
    with zipfile.ZipFile(module_apk, 'r') as zip_file:
        raw = zip_file.read('AndroidManifest.xml')
    axml, _ = AXML.from_axml(raw)
    return axml.to_xml()


def read_package(module_apk: os.PathLike) -> typing.Optional[str]:
    return read_manifest(module_apk).get('package')


def collect_components(module_apk: os.PathLike) -> ModuleComponents:
    """Read the manifest of an AGP-built module APK and return the parts that belong in the host manifest."""
    manifest = read_manifest(module_apk)
    return extract_components(manifest, manifest.get('package'))


def _is_already_declared(parent: lxml.etree.Element, element: lxml.etree.Element) -> bool:
    name = element.get(ManifestKeys.NAME)
    authorities = element.get(ManifestKeys.AUTHORITIES)
    for existing in parent:
        if not isinstance(existing.tag, str):
            continue
        if existing.tag == element.tag and name is not None and existing.get(ManifestKeys.NAME) == name:
            return True
        if authorities is not None and existing.get(ManifestKeys.AUTHORITIES) == authorities:
            return True
    return False


def _append_new(parent: lxml.etree.Element, elements: typing.List[lxml.etree.Element],
                insert_at: typing.Optional[int] = None) -> None:
    for element in elements:
        if _is_already_declared(parent, element):
            print(f'[+] <{element.tag}> {element.get(ManifestKeys.NAME)} is already declared, skipping')
            continue
        if insert_at is None:
            parent.append(element)
        else:
            parent.insert(insert_at, element)
            insert_at += 1


def find_application(manifest: lxml.etree.Element) -> lxml.etree.Element:
    application = manifest.find('application')
    if application is None:
        application = manifest.find('.//application')
    if application is None:
        raise ValueError('No <application> tag found in the manifest')
    return application


def merge_components(host_manifest: lxml.etree.Element, components: ModuleComponents) -> None:
    application = find_application(host_manifest)
    _append_new(application, components.application)
    children = list(host_manifest)
    insert_at = children.index(application) if application in children else len(children)
    _append_new(host_manifest, components.root, insert_at)
