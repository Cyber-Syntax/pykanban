# Configuration Documentation

Default config file is created in the users home directory as `~/.config/pykanban/config.yml` on the first run of the application.

Default settings in config.py:

```python
@dataclass
class Settings:
    """Configuration settings for pykanban."""

    projects_dir: Path = Path.home() / "Documents" / "pykanban-projects"
```

Example user config.yml:

```yml
projects_dir: /home/developer/Documents/kanban-todos
```
