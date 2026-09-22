import dataclasses
from pathlib import Path
from importlib.resources import files
import enum

APKTOOL_PATH = files('stitch').joinpath('bin/apktool_3.0.2.jar')
FASTSIGNER_PATH = files('stitch').joinpath('bin/fastsigner')
DEBUG_KEY_PATH = files('stitch').joinpath('bin/debug.pk8')
DEBUG_CERT_PATH = files('stitch').joinpath('bin/debug.pem')
EXTRACTED_PATH = 'extracted'
BUNDLE_DIR_PATH = 'bundle_apks'
BUNDLE_APK_EXTRACTED_PATH = Path('bundle')
SMALI_GENERATOR_TEMP_PATH = './smali_generator'
SMALI_EXTRACTED_PATH = './smali_extracted'
SMALI_GENERATOR_OUTPUT_PATH = './smali_generator.apk'
ARTIFACTORY_PATH = Path('artifactory.json')


class ManifestKeys(enum.StrEnum):
    EXPORTED = '{http://schemas.android.com/apk/res/android}exported'
    NAME = '{http://schemas.android.com/apk/res/android}name'
    AUTHORITIES = '{http://schemas.android.com/apk/res/android}authorities'
    TARGET_ACTIVITY = '{http://schemas.android.com/apk/res/android}targetActivity'
    INIT_ORDER = "{http://schemas.android.com/apk/res/android}initOrder"


ANDROID_MANIFEST_RELEVANT_TAGS = ['activity', 'activity-alias', 'provider', 'receiver', 'service']
ANDROID_MANIFEST_ROOT_TAGS = ['uses-permission', 'uses-permission-sdk-23', 'uses-feature', 'queries']

@dataclasses.dataclass
class ExternalModule:
    module_path: Path
    invoke_line: str