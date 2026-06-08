"""TaskManager handles task lifecycle operations: create, update, move..."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pykanban.error import ParseError
from pykanban.exceptions import WriteError
from pykanban.logger import get_logger
from pykanban.models import Priority, Status, Task
from pykanban.parser import write_project, write_task
from pykanban.task_utils import (
    build_task_file_path,
    insert_into_column,
    remove_from_columns,
    reorder_in_column,
)
from pykanban.utils import generate_task_id

if TYPE_CHECKING:
    from pykanban.state import AppState


logger = get_logger(__name__)


class TaskManager:
    """Responsible for task lifecylce operations: create, update, move, delete."""

    def __init__(self, state: AppState):
        """Initialize TaskManager with application state.

        Args:
            state: The application state to operate on.
        """
        self.state: AppState = state

    def create_task(
        self,
        title: str,
        status: Status,
        priority: Priority,
        body: str,
    ) -> Task:
        """Create a new task and persist it.

        Args:
            title: Task title.
            status: Task status.
            priority: Task priority.
            body: Task markdown body.

        Returns:
            The created task.
        """
        logger.debug(
            "Creating task: title=%s, status=%s, priority=%s",
            title,
            status,
            priority,
        )
        project = self.state.projects.get_active()
        task_id = generate_task_id(self.state.tasks)
        now = datetime.now()

        task = Task(
            id=task_id,
            schema=1,
            title=title.strip(),
            status=status,
            priority=priority,
            raw_body=body,
            created=now,
            updated=now,
        )

        self.state.tasks.put(task)
        project.column_order = insert_into_column(
            project.column_order, status.value, task_id
        )

        try:
            write_task(
                task,
                build_task_file_path(project.folder_path, task.title, task_id),
            )
            write_project(project)
        except WriteError as e:
            logger.exception("Failed to write task: %s", task_id)
            self.state.errors.append(ParseError(path=e.path, reason=e.reason))

        logger.info("Task created: %s", task)
        return task

    # TODO: create a new TaskUpdate model for fields type safety
    def update_task(self, task_id: str, fields: dict) -> Task:
        """Update task fields and persist changes.

        Args:
            task_id: Task ID to update.
            fields: Dict of fields to update.

        Returns:
            Updated task.
        """
        logger.debug("Updating task: %s", task_id)
        task = self.state.tasks.get(task_id)
        project = self.state.projects.get_active()
        old_path = build_task_file_path(
            project.folder_path, task.title, task_id
        )

        # Extract position and remove it from fields
        position = fields.get("position")
        new_status = fields.get("status", task.status)

        # Extract fields to update
        # TODO: make it readeable
        fields = {
            k: v for k, v in fields.items() if k not in {"position", "status"}
        }

        if new_status != task.status:
            project.column_order = remove_from_columns(
                project.column_order, task_id
            )
            project.column_order = insert_into_column(
                project.column_order, new_status.value, task_id, position
            )
            task.status = new_status
        elif position is not None:
            project.column_order = reorder_in_column(
                project.column_order, task_id, position
            )

        if "title" in fields:
            task.title = str(fields["title"]).strip()
        if "priority" in fields:
            task.priority = fields["priority"]
        if "raw_body" in fields:
            task.raw_body = fields["raw_body"]

        task.updated = datetime.now()

        # TODO: write test
        try:
            # Remove old path if it exists and is different from the new path
            new_path = build_task_file_path(
                project.folder_path, task.title, task_id
            )
            if old_path != new_path and old_path.exists():
                old_path.unlink()

            # Save the task to the new path
            write_task(task, new_path)
            write_project(project)
        except WriteError as e:
            logger.exception("Failed to write task: %s", task_id)
            self.state.errors.append(ParseError(path=e.path, reason=e.reason))

        logger.info("Task updated: %s", task)
        return task

    def move_task(
        self, task_id: str, new_status: Status, position: int
    ) -> Task:
        """Move a task across columns and persist changes.

        Args:
            task_id: Task ID to move.
            new_status: Destination status.
            position: Index in destination column.

        Returns:
            Updated task.
        """
        logger.debug("Moving task: %s", task_id)
        task = self.state.tasks.get(task_id)
        project = self.state.projects.get_active()

        project.column_order = remove_from_columns(
            project.column_order, task_id
        )
        project.column_order = insert_into_column(
            project.column_order, new_status.value, task_id, position
        )
        task.status = new_status
        task.updated = datetime.now()

        # TODO: write tests
        try:
            write_task(
                task,
                build_task_file_path(project.folder_path, task.title, task_id),
            )
            write_project(project)
        except WriteError as e:
            logger.exception("Failed to write task: %s", task_id)
            self.state.errors.append(ParseError(path=e.path, reason=e.reason))

        logger.info("Task moved to %s: %s", new_status.value, task_id)
        return task

    def delete_task(self, task_id: str) -> None:
        """Delete a task and remove it from the board.

        Args:
            task_id: Task ID to delete.
        """
        logger.debug("Deleting task: %s", task_id)
        task = self.state.tasks.get(task_id)
        project = self.state.projects.get_active()
        path = build_task_file_path(project.folder_path, task.title, task_id)

        # TODO: write tests
        try:
            path.unlink()
        except OSError as e:
            logger.exception("Failed to delete task: %s", task_id)
            self.state.errors.append(ParseError(path=path, reason=str(e)))
            return

        project.column_order = remove_from_columns(
            project.column_order, task_id
        )
        self.state.tasks.remove(task_id)

        # TODO: write tests
        try:
            write_project(project)
        except WriteError as e:
            logger.exception("Failed to write project: %s", project.project_id)
            self.state.errors.append(ParseError(path=e.path, reason=e.reason))

        logger.info("Task deleted: %s", task_id)
