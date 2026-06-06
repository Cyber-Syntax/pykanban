"""Parse and write functions for Task and Project."""

from __future__ import annotations

from datetime import datetime
from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from pykanban.error import ParseError
from pykanban.exceptions import WriteError  # noqa: F401 — re-raised by callers
from pykanban.file_handler import atomic_write
from pykanban.logger import get_logger
from pykanban.models import Priority, Project, Status, Task
from pykanban.utils import flow_id_list

yaml = YAML()

logger = get_logger(__name__)


def parse_task(path: Path) -> Task | ParseError:
    """Parse a Task from a markdown file with YAML front matter.

    Args:
        path: Path to the .md file.

    Returns:
        Task on success, ParseError on any failure.
    """
    logger.debug("Parsing task from %s", path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.exception("Failed to read file %s", path)
        return ParseError(path=path, reason=str(e))

    if not text.startswith("---\n"):
        logger.error("Missing YAML front matter in %s", path)
        return ParseError(path=path, reason="Missing YAML front matter")

    _, _, rest = text.partition("---\n")
    frontmatter, sep, raw_body = rest.partition("---\n")
    if not sep:
        logger.error("Missing closing YAML front matter in %s", path)
        return ParseError(
            path=path, reason="Missing closing YAML front matter"
        )

    logger.debug("Parsing YAML front matter in %s", path)
    try:
        data = yaml.load(frontmatter)
    except YAMLError as e:
        logger.exception("YAML parsing error in %s", path)
        return ParseError(path=path, reason=f"YAML parsing error: {e}")

    # make sure yaml front matter isn't empty
    if not isinstance(data, dict):
        logger.error("YAML front matter is not a mapping in %s", path)
        return ParseError(
            path=path, reason="YAML front matter must be a mapping"
        )

    logger.debug("Validating fields in %s", path)
    for field in (
        "id",
        "schema",
        "title",
        "status",
        "priority",
        "created",
        "updated",
    ):
        if field not in data:
            logger.error("Missing required field %s in %s", field, path)
            return ParseError(
                path=path, reason=f"Missing required field: {field}"
            )

    try:
        status = Status(str(data["status"]))
    except ValueError:
        logger.exception("Invalid status value %s in %s", data["status"], path)
        return ParseError(
            path=path, reason=f"Invalid status value: {data['status']}"
        )

    try:
        priority = Priority(str(data["priority"]))
    except ValueError:
        logger.exception(
            "Invalid priority value %s in %s", data["priority"], path
        )
        return ParseError(
            path=path, reason=f"Invalid priority value: {data['priority']}"
        )

    try:
        created = datetime.fromisoformat(data["created"])
        updated = datetime.fromisoformat(data["updated"])
    except ValueError as e:
        logger.exception(
            "Invalid datetime format %s in %s", data["created"], path
        )
        return ParseError(path=path, reason=f"Invalid datetime format: {e}")

    return Task(
        id=str(data["id"]),
        schema=int(data["schema"]),
        title=str(data["title"]),
        status=status,
        priority=priority,
        raw_body=raw_body,
        created=created,
        updated=updated,
    )


def write_task(task: Task, path: Path) -> None:
    """Serialize a Task to a markdown file with YAML front matter.

    Side-effect: updates task.updated to the current time before writing.

    Args:
        task: Task to serialize.
        path: Destination file path (created or overwritten atomically).

    Raises:
        WriteError: Propagated from atomic_write on any OS-level failure.
    """
    logger.debug("Writing task %s to %s", task.id, path)
    task.updated = datetime.now()
    data = {
        "id": task.id,
        "schema": task.schema,
        "title": task.title,
        "status": task.status.value,
        "priority": task.priority.value,
        "created": task.created.isoformat(),
        "updated": task.updated.isoformat(),
    }
    stream = StringIO()
    yaml.dump(data, stream)
    content = f"---\n{stream.getvalue().strip()}\n---\n{task.raw_body}"
    atomic_write(path, content)


def parse_project(path: Path) -> Project | ParseError:
    """Parse a Project from a metadata.yml file.

    Args:
        path: Path to the metadata.yml file.

    Returns:
        Project on success, ParseError on any failure.
    """
    logger.debug("Parsing project from %s", path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.exception("Error reading file %s", path)
        return ParseError(path=path, reason=f"Error reading file: {e}")

    try:
        data = yaml.load(text)
    except YAMLError as e:
        logger.exception("YAML parsing error in %s", path)
        return ParseError(path=path, reason=f"YAML parsing error: {e}")

    logger.debug("Validating fields in %s", path)
    for field in (
        "project_id",
        "schema",
        "title",
        "created",
        "updated",
        "archived",
        "column_order",
    ):
        if field not in data:
            logger.error("Missing required field: %s in %s", field, path)
            return ParseError(
                path=path, reason=f"Missing required field: {field}"
            )

    try:
        created = datetime.fromisoformat(data["created"])
        updated = datetime.fromisoformat(data["updated"])
    except ValueError as e:
        logger.exception("Invalid datetime format in %s", path)
        return ParseError(path=path, reason=f"Invalid datetime format: {e}")

    return Project(
        project_id=str(data["project_id"]),
        schema=int(data["schema"]),
        title=str(data["title"]),
        description=str(data.get("description", "")).strip(),
        created=created,
        updated=updated,
        archived=bool(data["archived"]),
        column_order=dict(data["column_order"]),
        folder_path=path.parent,
    )


def write_project(project: Project) -> None:
    """Serialize a Project to its metadata.yml file.

    Side-effect: updates project.updated to the current time before writing.

    Args:
        project: Project to serialize.

    Raises:
        WriteError: Propagated from atomic_write on any OS-level failure.
    """
    logger.debug("Writing project to %s", project.folder_path / "metadata.yml")
    project.updated = datetime.now()
    data = {
        "project_id": project.project_id,
        "schema": project.schema,
        "title": project.title,
        "description": project.description,
        "created": project.created.isoformat(),
        "updated": project.updated.isoformat(),
        "archived": project.archived,
        "column_order": {
            status: flow_id_list(ids)
            for status, ids in project.column_order.items()
        },
    }
    stream = StringIO()
    yaml.dump(data, stream)
    atomic_write(
        project.folder_path / "metadata.yml",
        stream.getvalue().strip(),
    )
