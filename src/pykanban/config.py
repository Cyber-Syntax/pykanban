"""Global configuration for pykanban."""

from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML

# Create .config/pykanban/config.yml and keep the projects_dir
# load settings function to load from config.yml

CONFIG_DIR = Path.home() / ".config" / "pykanban"
CONFIG_FILE = CONFIG_DIR / "config.yml"

# ruamel.yaml explanation:
# - yaml=YAML(typ='safe')   # default, if not specfied, is 'rt' (round-trip)
yaml = YAML()


@dataclass
class Settings:
    """Configuration settings for pykanban."""

    projects_dir: Path = Path.home() / "Documents" / "pykanban-projects"


def load_settings() -> Settings:
    """Load settings from the config file.

    No directories or files are created here; that responsibility
    is belong to save_settings or bootstrap_settings.

    Returns:
        Settings: The loaded settings, or default values if no config file exists.
    """

    # Default settings - this is what the UI shows initially
    default_settings = Settings()

    # If there is no config file, just return the default
    if not CONFIG_FILE.exists():
        return default_settings

    # The file exists, read it
    with CONFIG_FILE.open() as f:
        data = yaml.load(f)

    # Pull the project_dir from the config, or use the default
    project_dir = Path(data.get("projects_dir", str(Settings().projects_dir)))
    return Settings(projects_dir=Path(project_dir).expanduser().resolve())


def save_settings(settings: Settings) -> None:
    """Save settings to the config file.

    The config directory is created if it doesn't exist.
    This is the only place that writes to the config file.
    """

    # Create config directory if it doesn't exist
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    with CONFIG_FILE.open("w") as f:
        yaml.dump({"projects_dir": str(settings.projects_dir.resolve())}, f)
