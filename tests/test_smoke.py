from complaint_triage import __version__


def test_package_exposes_initial_version() -> None:
    """The repository foundation installs the expected package."""
    assert __version__ == "0.1.0"
