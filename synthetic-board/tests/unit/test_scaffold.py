"""Smoke test: package imports and version."""

from sboard import __version__


def test_version() -> None:
    assert __version__ == "0.1.0"


def test_cli_import() -> None:
    from sboard.cli import app  # noqa: F401
