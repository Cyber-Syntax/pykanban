"""Pytest configuration for UI tests."""

import os

import pytest
from PySide6.QtWidgets import QApplication

# Disable Qt for import-only tests
os.environ["QT_QPA_PLATFORM"] = "minimal"


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create QApplication for all tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(scope="session", autouse=True)
def skip_widget_tests():
    """Skip widget instantiation tests in headless environment."""
    # Just a marker - actual skipping will be in tests if needed
