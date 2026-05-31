from datetime import datetime
from pathlib import Path

import pytest

from pykanban.error import ParseError
from pykanban.models import Priority, Project, Status, Task
from pykanban.parser import (
    parse_project,
    parse_task,
    write_project,
    write_task,
)


class TestParseTask:
    def test_reads_yaml_front_matter(self, tmp_path: Path) -> None:
        task_file = tmp_path / "task.md"
        task_file.write_text(
            """---
id: t_001
schema: 1
title: Example Task
status: todo
priority: medium
created: "2026-05-31T10:00:00"
updated: "2026-05-31T11:00:00"
---
Task body here.
"""
        )

        result = parse_task(task_file)

        assert isinstance(result, Task)
        assert result.id == "t_001"
        assert result.schema == 1
        assert result.title == "Example Task"
        assert result.status == Status.TODO
        assert result.priority == Priority.MEDIUM
        assert result.raw_body == "Task body here.\n"
        assert result.created == datetime.fromisoformat("2026-05-31T10:00:00")
        assert result.updated == datetime.fromisoformat("2026-05-31T11:00:00")

    def test_returns_parse_error_when_file_missing(
        self, tmp_path: Path
    ) -> None:
        missing = tmp_path / "missing.md"

        result = parse_task(missing)

        assert isinstance(result, ParseError)
        assert result.path == missing

    def test_requires_yaml_front_matter(self, tmp_path: Path) -> None:
        task_file = tmp_path / "task.md"
        task_file.write_text("No front matter here.\n")

        result = parse_task(task_file)

        assert isinstance(result, ParseError)
        assert result.reason == "Missing YAML front matter"

    def test_requires_closing_front_matter(self, tmp_path: Path) -> None:
        task_file = tmp_path / "task.md"
        task_file.write_text(
            """---
id: t_001
schema: 1
title: Example Task
status: todo
priority: medium
created: "2026-05-31T10:00:00"
updated: "2026-05-31T11:00:00"
Task body here.
"""
        )

        result = parse_task(task_file)

        assert isinstance(result, ParseError)
        assert result.reason == "Missing closing YAML front matter"

    @pytest.mark.parametrize(
        ("frontmatter", "expected_reason"),
        [
            (
                """id: t_001
schema: 1
title: Example Task
status: todo
priority: medium
created: "2026-05-31T10:00:00"
updated: "2026-05-31T11:00:00"
bad: [yaml
""",
                "YAML parsing error:",
            ),
            (
                """schema: 1
title: Example Task
status: todo
priority: medium
created: "2026-05-31T10:00:00"
updated: "2026-05-31T11:00:00"
""",
                "Missing required field: id",
            ),
            (
                """id: t_001
schema: 1
title: Example Task
priority: medium
created: "2026-05-31T10:00:00"
updated: "2026-05-31T11:00:00"
""",
                "Missing required field: status",
            ),
            (
                """id: t_001
schema: 1
title: Example Task
status: invalid
priority: medium
created: "2026-05-31T10:00:00"
updated: "2026-05-31T11:00:00"
""",
                "Invalid status value: invalid",
            ),
            (
                """id: t_001
schema: 1
title: Example Task
status: todo
priority: invalid
created: "2026-05-31T10:00:00"
updated: "2026-05-31T11:00:00"
""",
                "Invalid priority value: invalid",
            ),
            (
                """id: t_001
schema: 1
title: Example Task
status: todo
priority: medium
created: not-a-datetime
updated: "2026-05-31T11:00:00"
""",
                "Invalid datetime format:",
            ),
        ],
    )
    def test_rejects_invalid_front_matter(
        self,
        tmp_path: Path,
        frontmatter: str,
        expected_reason: str,
    ) -> None:
        task_file = tmp_path / "task.md"
        task_file.write_text(f"---\n{frontmatter}---\nBody\n")

        result = parse_task(task_file)

        assert isinstance(result, ParseError)
        assert expected_reason in result.reason


class TestWriteTask:
    def test_serializes_task_and_updates_timestamp(
        self,
        tmp_path: Path,
    ) -> None:
        task = Task(
            id="t_001",
            schema=1,
            title="Example Task",
            status=Status.DOING,
            priority=Priority.HIGH,
            raw_body="Task body here.\n",
            created=datetime.fromisoformat("2026-05-31T10:00:00"),
            updated=datetime.fromisoformat("2026-05-31T11:00:00"),
        )
        path = tmp_path / "task.md"

        original_updated = task.updated
        write_task(task, path)

        written = path.read_text(encoding="utf-8")

        assert path.exists()
        assert task.updated > original_updated
        assert "id: t_001" in written
        assert "title: Example Task" in written
        assert "status: doing" in written
        assert "priority: high" in written
        assert "Task body here." in written

        parsed = parse_task(path)
        assert isinstance(parsed, Task)
        assert parsed.id == task.id
        assert parsed.title == task.title
        assert parsed.status == task.status
        assert parsed.priority == task.priority
        assert parsed.raw_body == task.raw_body


class TestParseProject:
    def test_reads_metadata_file(self, tmp_path: Path) -> None:
        project_folder = tmp_path / "project"
        project_folder.mkdir()
        metadata = project_folder / "metadata.yml"
        metadata.write_text(
            """project_id: p_001
schema: 1
title: Example Project
description: Example description
created: "2026-05-31T10:00:00"
updated: "2026-05-31T11:00:00"
archived: false
column_order:
  backlog: []
  todo:
    - t_001
  doing: []
  done: []
"""
        )

        result = parse_project(metadata)

        assert isinstance(result, Project)
        assert result.project_id == "p_001"
        assert result.schema == 1
        assert result.title == "Example Project"
        assert result.description == "Example description"
        assert result.archived is False
        assert result.folder_path == project_folder
        assert result.column_order[Status.TODO.value] == ["t_001"]

    def test_returns_parse_error_when_file_missing(
        self,
        tmp_path: Path,
    ) -> None:
        missing = tmp_path / "metadata.yml"

        result = parse_project(missing)

        assert isinstance(result, ParseError)
        assert result.path == missing

    @pytest.mark.parametrize(
        ("content", "expected_reason"),
        [
            (
                """not: valid: yaml: [broken
""",
                "YAML parsing error:",
            ),
            (
                """schema: 1
title: Example Project
created: "2026-05-31T10:00:00"
updated: "2026-05-31T11:00:00"
archived: false
column_order: {}
""",
                "Missing required field: project_id",
            ),
            (
                """project_id: p_001
schema: 1
title: Example Project
created: not-a-datetime
updated: "2026-05-31T11:00:00"
archived: false
column_order: {}
""",
                "Invalid datetime format:",
            ),
        ],
    )
    def test_rejects_invalid_metadata(
        self,
        tmp_path: Path,
        content: str,
        expected_reason: str,
    ) -> None:
        metadata = tmp_path / "metadata.yml"
        metadata.write_text(content)

        result = parse_project(metadata)

        assert isinstance(result, ParseError)
        assert expected_reason in result.reason


class TestWriteProject:
    def test_serializes_project_and_updates_timestamp(
        self,
        tmp_path: Path,
    ) -> None:
        project_folder = tmp_path / "project"
        project_folder.mkdir()
        project = Project(
            project_id="p_001",
            schema=1,
            title="Example Project",
            description="Example description",
            created=datetime.fromisoformat("2026-05-31T10:00:00"),
            updated=datetime.fromisoformat("2026-05-31T11:00:00"),
            archived=True,
            column_order={
                Status.BACKLOG.value: [],
                Status.TODO.value: ["t_001"],
                Status.DOING.value: [],
                Status.DONE.value: [],
            },
            folder_path=project_folder,
        )

        original_updated = project.updated
        write_project(project)

        metadata = project_folder / "metadata.yml"
        written = metadata.read_text(encoding="utf-8")

        assert metadata.exists()
        assert project.updated > original_updated
        assert "project_id: p_001" in written
        assert "title: Example Project" in written
        assert "description: Example description" in written
        assert "archived: true" in written
        assert "t_001" in written

        parsed = parse_project(metadata)
        assert isinstance(parsed, Project)
        assert parsed.project_id == project.project_id
        assert parsed.title == project.title
        assert parsed.description == project.description
        assert parsed.archived is True
        assert parsed.column_order[Status.TODO.value] == ["t_001"]
