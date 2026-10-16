import zipfile

from stitch.patcher import inject_json_asset


def test_inject_json_asset_adds_entry_and_keeps_others(tmp_path):
    apk = tmp_path / 'a.apk'
    with zipfile.ZipFile(apk, 'w') as z:
        z.writestr('classes.dex', b'dex', compress_type=zipfile.ZIP_STORED)
        z.writestr('assets/patcher/artifactory.json', b'{"OLD": "1"}')
    inject_json_asset(apk, 'assets/patcher/artifactory.json', {'B': '2', 'A': '1'})
    with zipfile.ZipFile(apk) as z:
        assert z.read('assets/patcher/artifactory.json') == b'{"A": "1", "B": "2"}'
        assert z.read('classes.dex') == b'dex'
        assert z.getinfo('classes.dex').compress_type == zipfile.ZIP_STORED
        assert z.namelist().count('assets/patcher/artifactory.json') == 1
