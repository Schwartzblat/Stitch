import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
SOURCE_BINARY = PROJECT_ROOT / 'src' / 'stitch' / 'bin' / 'fastsigner'


@pytest.fixture
def non_executable_source():
    """A freshly downloaded fastsigner release is 0644; only a git clone restores the bit."""
    original = SOURCE_BINARY.stat().st_mode
    SOURCE_BINARY.chmod(original & ~0o111)
    yield
    SOURCE_BINARY.chmod(original)


def test_build_py_forces_fastsigner_executable(tmp_path, non_executable_source):
    subprocess.run(
        [sys.executable, 'setup.py', 'build_py', '--build-lib', str(tmp_path)],
        cwd=PROJECT_ROOT, check=True, capture_output=True,
    )

    assert (tmp_path / 'stitch' / 'bin' / 'fastsigner').stat().st_mode & 0o111 == 0o111
