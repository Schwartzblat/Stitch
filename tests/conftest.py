import lxml.etree

ANDROID_NS = 'http://schemas.android.com/apk/res/android'
TOOLS_NS = 'http://schemas.android.com/tools'


def android(name: str) -> str:
    return f'{{{ANDROID_NS}}}{name}'


def build_manifest(inner: str, package: str = 'com.mod') -> lxml.etree.Element:
    """Build a manifest tree the way androguard hands one back: clark-notation android attributes."""
    return lxml.etree.fromstring(
        f'<manifest xmlns:android="{ANDROID_NS}" xmlns:tools="{TOOLS_NS}" package="{package}">{inner}</manifest>'
    )


def build_element(xml: str, package: str = 'com.mod') -> lxml.etree.Element:
    """A single manifest element, carrying the android/tools namespace declarations it needs."""
    return build_manifest(xml, package)[0]


def build_module_apk(path, inner: str, package: str = 'com.mod', extra: dict = None):
    """A zip holding a real binary AndroidManifest.xml, the way an AGP-built module APK does."""
    import zipfile
    from pyaxml import AXML

    axml = AXML()
    axml.from_xml(
        f'<manifest xmlns:android="{ANDROID_NS}" package="{package}">{inner}</manifest>'
    )
    axml.compute()
    with zipfile.ZipFile(path, 'w') as zip_file:
        zip_file.writestr('AndroidManifest.xml', axml.pack())
        for name, value in (extra or {}).items():
            data, compress = value if isinstance(value, tuple) else (value, zipfile.ZIP_DEFLATED)
            zip_file.writestr(name, data, compress_type=compress)
    return path


def write_binary_manifest(path, inner: str, package: str = 'com.host'):
    from pyaxml import AXML

    axml = AXML()
    axml.from_xml(f'<manifest xmlns:android="{ANDROID_NS}" package="{package}">{inner}</manifest>')
    axml.compute()
    path.write_bytes(axml.pack())
    return path


def read_binary_manifest(path) -> lxml.etree.Element:
    from pyaxml import AXML

    axml, _ = AXML.from_axml(path.read_bytes())
    return axml.to_xml()


def build_apk_zip(path, entries: dict):
    """A zip standing in for an APK. Values are bytes, or (bytes, compress_type) to pin the compression."""
    import zipfile

    with zipfile.ZipFile(path, 'w') as zip_file:
        for name, value in entries.items():
            data, compress = value if isinstance(value, tuple) else (value, zipfile.ZIP_DEFLATED)
            zip_file.writestr(name, data, compress_type=compress)
    return path
