"""Smoke test: the package is installed and its version has a single source."""

from importlib.metadata import version

import irpipe


def test_installed_version_matches_package_version() -> None:
    assert version("irpipe") == irpipe.__version__
