"""Error banner widget for parse and conflict messages.

Uses PySide6 for UI rendering.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from pykanban.error import ErrorEntry
from pykanban.logger import get_logger

logger = get_logger(__name__)


class ErrorBanner(QWidget):
    """Banner that displays parse/conflict errors."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the error banner."""
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._labels: list[QLabel] = []
        self.setVisible(False)

    def set_errors(self, errors: Sequence[ErrorEntry]) -> None:
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
            logger.debug("Clearing error banner")
            self.setVisible(False)
            return

        logger.info("Displaying %d errors in error banner", len(errors))

        # Add new labels for each error
        for error in errors:
            logger.debug(
                "Error banner entry: path=%s reason=%s",
                error.path,
                error.reason,
            )

            label = QLabel(f"{error.path}: {error.reason}")
            label.setWordWrap(True)
            label.setStyleSheet("color: red;")
            self._layout.addWidget(label)
            self._labels.append(label)

        self.setVisible(True)
