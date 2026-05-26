"""Models for the PyKanban application."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from io import StringIO
from typing import TYPE_CHECKING

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedSeq
from ruamel.yaml.error import YAMLError
from ruamel.yaml.scalarstring import SingleQuotedScalarString

from pykanban.repository import file_io

if TYPE_CHECKING:
    from pathlib import Path

    from pykanban.core.store import TaskStore

# ruamel.yaml is used to preserve the order of fields in the YAML front matter
# ruamel.yaml use typ="safe" default when not specified
yaml = YAML()


def _flow_id_list(ids: list[str]) -> CommentedSeq:
    """Return a flow-style YAML sequence of single-quoted task ID strings.

    Two problems are solved here:
        - Flow style: renders as [id, id] instead of block "- id" lines.
        - Signle-quoted strings: prevents ruamel/YAML 1.1 from casting IDs that
        look like numbers (e.g. "0e532197" → float 0.0) back to non-string
        types on the next load.

    Args:
        ids: Task ID strings to wrap.

    Returns:
        A CommentedSeq configured for flow-style output.1
    """
    seq = CommentedSeq([SingleQuotedScalarString(i) for i in ids])
    seq.fa.set_flow_style()
    return seq


class Status(Enum):
    """Status of a task."""

    BACKLOG = "backlog"
    TODO = "todo"
    DOING = "doing"
    DONE = "done"


class Priority(Enum):
    """Priority of a task."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ParseError:
    """Error parsing a task."""

    path: Path
    reason: str


@dataclass
class Task:
    """Task."""

    id: str
    schema: int
    title: str
    status: Status
    priority: Priority
    raw_body: str
    created: datetime
    updated: datetime

    @classmethod
    def from_file(cls, path: Path) -> Task | ParseError:
        """Parse a task from a file."""

        # read the file content as UTF-8 text
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            return ParseError(path=path, reason=str(e))

        # check if the file starts with a YAML front matter
        if not text.startswith("---\n"):
            return ParseError(path=path, reason="Missing YAML front matter")

        # split the text into front matter and body
        _, _, rest = text.partition("---\n")
        frontmatter, sep, raw_Body = rest.partition("---\n")
        if sep == "":
            return ParseError(
                path=path, reason="Missing closing YAML front matter"
            )

        # parse the front matter as YAML
        try:
            data = yaml.load(frontmatter)
        except YAMLError as e:
            return ParseError(path=path, reason=f"YAML parsing error: {e}")

        # validate required fields
        required_fields = [
            "id",
            "schema",
            "title",
            "status",
            "priority",
            "created",
            "updated",
        ]
        for field in required_fields:
            if field not in data:
                return ParseError(
                    path=path, reason=f"Missing required field: {field}"
                )

        try:
            status: Status = Status(str(data["status"]))
        except ValueError:
            return ParseError(
                path=path, reason=f"Invalid status value: {data['status']}"
            )

        try:
            priority: Priority = Priority(str(data["priority"]))
        except ValueError:
            return ParseError(
                path=path, reason=f"Invalid priority value: {data['priority']}"
            )

        try:
            created: datetime = datetime.fromisoformat(data["created"])
        except ValueError:
            return ParseError(
                path=path,
                reason=f"Invalid created datetime format: {data['created']}",
            )

        try:
            updated: datetime = datetime.fromisoformat(data["updated"])
        except ValueError:
            return ParseError(
                path=path,
                reason=f"Invalid updated datetime format: {data['updated']}",
            )

        return cls(
            id=str(data["id"]),
            schema=int(data["schema"]),
            title=str(data["title"]),
            status=status,
            priority=priority,
            raw_body=raw_Body,
            created=created,
            updated=updated,
        )

    def write(self, path: Path) -> None:
        """Write the task to a Markdown file with YAML fornt matter.

        Updates "self.updated" to the current time before serializing
        so the on-disk timestamp always reflects the last actual save.

        Args:
            path: Destination file path (created or overwritten atomically)

        Raises:
            WriteError: Propagated from atomic_write on any OS-level failure.
        """
        self.updated = datetime.now()

        # create the YAML front matter
        data = {
            "id": self.id,
            "schema": self.schema,
            "title": self.title,
            "status": self.status.value,
            "priority": self.priority.value,
            "created": self.created.isoformat(),
            "updated": self.updated.isoformat(),
        }

        stream = StringIO()
        yaml.dump(data, stream)
        frontmatter = stream.getvalue().strip()

        content = f"---\n{frontmatter}\n---\n{self.raw_body}"
        file_io.atomic_write(path, content)


@dataclass
class Project:
    """Project."""

    project_id: str
    schema: int
    title: str
    description: str
    created: datetime
    updated: datetime
    archived: bool
    column_order: dict[str, list[str]]
    folder_path: Path

    @classmethod
    def from_file(cls, path: Path) -> Project | ParseError:
        """Parse a project metadata.yml from a file."""

        # read the file content as UTF-8 text
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            return ParseError(path=path, reason=f"Error reading file: {e}")
        # parse the content as YAML
        try:
            data = yaml.load(text)
        except YAMLError as e:
            return ParseError(path=path, reason=f"YAML parsing error: {e}")

        # validate required fields
        required_fields = [
            "project_id",
            "schema",
            "title",
            "created",
            "updated",
            "archived",
            "column_order",
        ]
        for field in required_fields:
            if field not in data:
                return ParseError(
                    path=path, reason=f"Missing required field: {field}"
                )

        try:
            created: datetime = datetime.fromisoformat(data["created"])
            updated: datetime = datetime.fromisoformat(data["updated"])
        except ValueError as e:
            return ParseError(
                path=path,
                reason=f"Invalid datetime format: {e}",
            )

        archived: bool = bool(data["archived"])

        column_order: dict[str, list[str]] = dict[str, list[str]](
            data["column_order"]
        )

        return cls(
            project_id=str(data["project_id"]),
            schema=int(data["schema"]),
            title=str(data["title"]),
            description=str(data["description"]).strip(),
            created=created,
            updated=updated,
            archived=bool(data["archived"]),
            column_order=column_order,
            folder_path=path.parent,
        )

    def write(self) -> None:
        """Write the project metadata to a metadata.yml file in the project folder.

        Updates "self.updated" to the current time before serializing.

        Raises:
            WriteError: Propagated from atomic_write on any OS-level self.failure.
        """
        self.updated = datetime.now()

        data = {
            "project_id": self.project_id,
            "schema": self.schema,
            "title": self.title,
            "description": self.description,
            "created": self.created.isoformat(),
            "updated": self.updated.isoformat(),
            "archived": self.archived,
            # each list is flow-style + quoted to prevent yaml 1.1 type coercion
            "column_order": {
                status: _flow_id_list(ids)
                for status, ids in self.column_order.items()
            },
        }

        stream = StringIO()
        yaml.dump(data, stream)
        content = stream.getvalue().strip()

        metadata_path = self.folder_path / "metadata.yml"
        file_io.atomic_write(metadata_path, content)

    def reconcile_order(
        self, known_ids: set[str], task_store: TaskStore
    ) -> None:
        """Reconcile the column order with the known task IDs."""

        # remove unknown task IDs from column_order
        for key, ids in self.column_order.items():
            self.column_order[key] = [id for id in ids if id in known_ids]

        # find missing ids
        present = {id_ for ids in self.column_order.values() for id_ in ids}
        missing = known_ids - present

        # append missing ids to their status column
        for task_id in missing:
            task = task_store.tasks_by_id.get(task_id)
            if not task:
                continue
            column_key = task.status.value
            self.column_order.setdefault(column_key, []).append(task_id)
