"""Models for the PyKanban application."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


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
