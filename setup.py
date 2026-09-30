"""Sits alongside pyproject.toml purely to keep bin/fastsigner executable.

setuptools copies package data with whatever mode the source file happens to
have, so a fastsigner dropped in straight from a release download (0644) builds
a wheel that pip installs non-executable. Forcing the bit here means the built
wheel is correct no matter how the binary arrived in the source tree, including
on Windows where there is no executable bit at all.
"""
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

EXECUTABLES = ('stitch/bin/fastsigner',)


class BuildPyWithExecutables(build_py):
    def run(self):
        super().run()
        for relative_path in EXECUTABLES:
            target = Path(self.build_lib, relative_path)
            if target.exists():
                target.chmod(target.stat().st_mode | 0o111)


setup(cmdclass={'build_py': BuildPyWithExecutables})
