"""In Memory Stored classes"""

from pykanban.config import Settings


class AppState:
    """Manages the application state."""

    def __init__(self, settings: Settings) -> None:
        """Initialize the app state."""
        self.settings = settings
