"""Error banner widget for parse and conflict messages.

Uses PySide6 for UI rendering.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class ErrorLike(Protocol):
    """Protocol for error-like objects."""

    path: Path
    reason: str


class ErrorBanner(QWidget):
    """Banner that displays parse/conflict errors."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the error banner."""
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._labels: list[QLabel] = []
        self.setVisible(False)

    def set_errors(self, errors: list[ErrorLike]) -> None:
        """Update the banner with a list of errors.

        Args:
            errors: Parse or conflict errors to display.
        """
        # Clear existing labels
        for label in self._labels:
            self._layout.removeWidget(label)
            label.deleteLater()
        self._labels.clear()

        if not errors:
            self.setVisible(False)
            return

        # Add new labels for each error
        for error in errors:
            label = QLabel(f"{error.path}: {error.reason}")
            label.setWordWrap(True)
            label.setStyleSheet("color: red;")
            self._layout.addWidget(label)
            self._labels.append(label)

        self.setVisible(True)
