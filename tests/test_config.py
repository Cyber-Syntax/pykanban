from pathlib import Path

import pytest
from ruamel.yaml import YAML

from pykanban.config import CONFIG_DIR, CONFIG_FILE, Settings, load_settings


@pytest.fixture
def isolated_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    """Replace CONFIG_DIR / CONFIG_FILE with a temporary location.

    The fixture yields a tuple(config_dir, config_file) that the tests
    can use to access the isolated configuration.
    """

    # Create a temporary config directory inside the pytest tmp_path
    temp_dir = tmp_path / "pykanban"
    temp_file = temp_dir / CONFIG_FILE

    # Monkey-patch the module constants so the code under test
    # uses the temporary config location
    monkeypatch.setattr("pykanban.config.CONFIG_DIR", temp_dir)
    monkeypatch.setattr("pykanban.config.CONFIG_FILE", temp_file)

    # Ensure a clean state before each test
    if temp_file.exists():
        temp_file.unlink()
    if temp_dir.exists():
        temp_dir.rmdir()

    return temp_dir, temp_file


def test_load_settings_return_defaults_when_no_file(
    isolated_config: tuple[Path, Path],
) -> None:
    """When the config file does not exist.

    load_settings() should return the default values.
    """
    config_dir, config_file = isolated_config

    # Sanity: make sure the file truly does not exist
    assert not config_file.exists()

    settings = load_settings()

    # The returned object should match the defaults defined in the Settings
    defaults = Settings()
    assert settings.projects_dir == defaults.projects_dir

    # load_settings must not have created the file or directory
    assert not config_file.exists()

    # The directory may be created lazily by the function, but
    # we expect to stay absent because we removed the creation code.
    # If you ever add lazy-creation, adjust this assertion accordingly.
    assert not config_dir.exists()


def test_load_settings_reads_existing_file(
    isolated_config: tuple[Path, Path],
) -> None:
    """When the config file exists.

    load_settings() should read and return the file contents.
    """
    config_dir, config_file = isolated_config

    # Prepare a custom projects_dir value
    custom_path = Path.home() / "my" / "custom" / "path"
    yaml = YAML()

    config_dir.mkdir(parents=True, exist_ok=True)
    with config_file.open("w") as f:
        yaml.dump({"projects_dir": str(custom_path)}, f)

    # Verify the file is really there
    assert config_file.exists()

    # Load the settings, it should reflect the value we wrote
    settings = load_settings()
    assert settings.projects_dir == custom_path.resolve()

    # Esnure the defaults are not returned
    default = Settings()
    assert settings.projects_dir != default.projects_dir
