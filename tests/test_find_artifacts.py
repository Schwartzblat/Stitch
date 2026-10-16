import zipfile

from stitch.artifactory_generator.SimpleArtifactoryFinder import SimpleArtifactoryFinder
from stitch.stitch import Stitch


class KeyFinder(SimpleArtifactoryFinder):
    def class_filter(self, data): return 'anchor' in data

    def extract_artifacts(self, artifacts, data):
        artifacts['FOUND'] = 'X.abc'; artifacts['OVERRIDDEN'] = 'finder'; self.is_found = True


def test_find_artifacts_runs_finders_and_applies_extras(tmp_path, monkeypatch):
    calls = []

    def fake_extract(apk_path, temp_path, *a, **k):
        calls.append(1)
        (temp_path / 'extracted' / 'smali').mkdir(parents=True)
        (temp_path / 'extracted' / 'smali' / 'A.smali').write_text('.class public LA;\nconst-string v0, "anchor"\n')

    monkeypatch.setattr('stitch.stitch.apk_utils.extract_apk', fake_extract)
    apk = tmp_path / 'in.apk'; zipfile.ZipFile(apk, 'w').writestr('classes.dex', b'dex')
    with Stitch(str(apk), temp_path=str(tmp_path / 'temp'), artifactory_list=[KeyFinder(None)],
                extra_artifacts={'OVERRIDDEN': 'extra'}) as s:
        assert s.find_artifacts() == {'FOUND': 'X.abc', 'OVERRIDDEN': 'extra'}
        assert s.find_artifacts() == {'FOUND': 'X.abc', 'OVERRIDDEN': 'extra'}
    assert calls == [1]
