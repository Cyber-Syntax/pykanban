"""Global configuration for pykanban."""

from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML, YAMLError

from pykanban.logger import get_logger

# Create .config/pykanban/config.yml and keep the projects_dir
# load settings function to load from config.yml

CONFIG_DIR = Path.home() / ".config" / "pykanban"
CONFIG_FILE = CONFIG_DIR / "config.yml"

# ruamel.yaml explanation:
# - yaml=YAML(typ='safe')   # default, if not specfied, is 'rt' (round-trip)
yaml = YAML()
logger = get_logger(__name__)


@dataclass
class Settings:
    """Configuration settings for pykanban."""

    projects_dir: Path = Path.home() / "Documents" / "pykanban-projects"
    log_level: str = "DEBUG"


class ConfigError(Exception):
    """Raised when the configuration is invalid."""

    def __init__(self, message: str):
        super().__init__(message)


def load_settings() -> Settings:
    """Load settings from the config file.

    No directories or files are created here; that responsibility
    is belong to save_settings or bootstrap_settings.

    Returns:
        Settings: The loaded settings, or default values if no config file exists.
    """

    # Default settings - this is what the UI shows initially
    default_settings = Settings()

    if not CONFIG_FILE.exists():
        logger.warning(
            "Config file %s does not exist, using default settings",
            CONFIG_FILE,
        )
        return default_settings

    # catch YAML errors and turn them into a ConfigError
    try:
        # The file exists, read it
        with CONFIG_FILE.open() as f:
            data = yaml.load(f)
        logger.debug("Config file loaded from %s", CONFIG_FILE)
    except YAMLError as e:
        logger.exception("Failed to load config file: ")
        raise ConfigError(
            f"The config file {CONFIG_FILE} is not valid YAML.\n"
            f"Details: {e}\n\nPlease fix or delete it and restart the app."
        ) from e

    # catch malformed yml, validate config.yml
    if not isinstance(data, dict) or "projects_dir" not in data:
        logger.warning(
            "Config file %s is not a mapping or missing 'projects_dir' key",
            CONFIG_FILE,
        )
        raise ConfigError(
            f"The config file {CONFIG_FILE} doesn't contain mapping\n"
            "Please fix or delete it and restart"
        )

    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR"}
    log_level = str(data.get("log_level", "DEBUG")).upper()
    if log_level not in valid_levels:
        logger.warning(
            "Invalid log level %r in config file, falling back to DEBUG",
            data.get("log_level"),
        )
        log_level = "DEBUG"

    # Pull the projects_dir from the config, or use the default
    projects_dir = Path(
        data.get("projects_dir", str(default_settings.projects_dir))
    )
    logger.info(
        "Settings resolved: projects_dir=%s log_level=%s",
        projects_dir,
        log_level,
    )
    return Settings(
        projects_dir=Path(projects_dir).expanduser().resolve(),
        log_level=log_level,
    )


def save_settings(settings: Settings) -> None:
    """Save settings to the config file.

    The config directory is created if it doesn't exist.
    This is the only place that writes to the config file.
    """
    logger.debug("Saving settings to %s", CONFIG_FILE)

    # Create config directory if it doesn't exist
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    with CONFIG_FILE.open("w") as f:
        yaml.dump(
            {
                "projects_dir": str(settings.projects_dir.resolve()),
                "log_level": settings.log_level,
            },
            f,
        )
    logger.info(
        "Saved settings to %s and project directory %s",
        CONFIG_FILE,
        settings.projects_dir,
    )

    settings.projects_dir.mkdir(parents=True, exist_ok=True)
