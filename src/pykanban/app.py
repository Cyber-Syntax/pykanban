"""KanbaAnApp Facade and Domain Managers for TaskManager and ProjectManager."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pykanban.models import Priority, Project, Status, Task
from pykanban.project_manager import ProjectManager
from pykanban.state import AppState
from pykanban.store import BoardView, TaskStore
from pykanban.task_manager import TaskManager

if TYPE_CHECKING:
    from pathlib import Path

    from pykanban.config import Settings
    from pykanban.error import ConflictWarning, ParseError


# TODO: make this pure function
def get_column(
    project: Project, status: Status, task_store: TaskStore
) -> list[Task]:
    """Return tasks in the column order for the given status."""
    column_ids = project.column_order.get(status.value, [])
    tasks: list[Task] = []
    for task_id in column_ids:
        task = task_store.tasks_by_id.get(task_id)
        if task and task.status == status:
            tasks.append(task)
    return tasks


class KanbanApp:
    """Application Facade. UI components hold this unified reference.

    It holds the unfied data structure and delegates actions to
    dedicated Domain Managers(TaskManager, ProjectManager).
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize AppStateManager facade with application settings.

        Args:
            settings: The application settings.
        """
        self.state: AppState = AppState.create(settings)
        self.tasks: TaskManager = TaskManager(self.state)
        self.projects: ProjectManager = ProjectManager(self.state)

    @property
    def projects_list(self) -> list[Project]:
        """Get the list of all projects."""
        return list(self.state.projects.projects_by_id.values())

    @property
    def active_project(self) -> Project | None:
        """Get the currently active project."""
        return self.state.projects.get_active()

    @property
    def errors(self) -> list[ParseError | ConflictWarning]:
        """Get the list of current errors and warnings."""
        return self.state.errors

    def get_task(self, task_id: str) -> Task | None:
        """Get a task by ID, or None if not found."""
        return self.state.tasks.tasks_by_id.get(task_id)

    def create_task(
        self, title: str, status: Status, priority: Priority, body: str
    ) -> Task:
        """Create a new task in the active project."""
        return self.tasks.create_task(title, status, priority, body)

    def move_task(
        self, task_id: str, new_status: Status, position: int
    ) -> Task:
        """Move a task across columns in the active project."""
        return self.tasks.move_task(task_id, new_status, position)

    def delete_task(self, task_id: str) -> None:
        """Delete a task by ID."""
        self.tasks.delete_task(task_id)

    def update_task(self, task_id: str, fields: dict) -> Task:
        """Update a task by ID with given fields."""
        return self.tasks.update_task(task_id, fields)

    def startup_scan(self, projects_dir: Path) -> None:
        """Perform the startup scan to load projects and tasks."""
        self.projects.startup_scan(projects_dir)

    def get_project(self, project_id: str) -> Project:
        """Get a project by ID."""
        return self.state.projects.projects_by_id[project_id]

    def set_active_project(self, project_id: str) -> None:
        """Set the active project by ID."""
        self.state.projects.set_active(project_id)

    def get_active_project(self) -> Project:
        """Get the currently active project."""
        return self.state.projects.get_active()

    def switch_project(self, project_id: str) -> None:
        """Switch the active project by ID."""
        self.projects.switch_project(project_id)

    def create_project(self, title: str, description: str) -> Project:
        """Create a new project.

        Args:
            title: Title of the new project.
            description: Description of the new project.
        """
        return self.projects.create_project(title, description)

    def rename_project(self, project_id: str, new_title: str) -> None:
        """Rename a project by ID.

        This changes the project's title and folder name.

        Args:
            project_id: ID of the project to rename.
            new_title: New title for the project.
        """
        self.projects.rename_project(project_id, new_title)

    def put_project(self, project: Project) -> None:
        """Add or update a project."""
        self.state.projects.put(project)

    def archive_project(self, project_id: str) -> None:
        """Archive a project by ID."""
        self.projects.archive_project(project_id)

    def unarchive_project(self, project_id: str) -> None:
        """Unarchive a project by ID."""
        self.projects.unarchive_project(project_id)

    def delete_project(self, project_id: str) -> None:
        """Delete a project by ID."""
        self.projects.delete_project(project_id)

    def get_board(self) -> BoardView:
        """Get the current board view.

        Returns:
            BoardView mapping statuses to ordered task lists.
        """
        project = self.state.projects.get_active()
        return BoardView(
            columns={
                Status.BACKLOG: get_column(
                    project, Status.BACKLOG, self.state.tasks
                ),
                Status.TODO: get_column(
                    project, Status.TODO, self.state.tasks
                ),
                Status.DOING: get_column(
                    project, Status.DOING, self.state.tasks
                ),
                Status.DONE: get_column(
                    project, Status.DONE, self.state.tasks
                ),
            }
        )

    def apply_external_changes(
        self, changed: list[Path], deleted: list[Path]
    ) -> None:
        """Relay external file changes to ProjectManager."""
        self.projects.apply_external_changes(changed, deleted)

    def handle_project_folder_deleted(self, folder_path: Path) -> None:
        """Relay an externaly deleted project folder to ProjectManager."""
        self.projects.handle_project_folder_deleted(folder_path)
