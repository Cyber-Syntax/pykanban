"""In-memory store classes for PyKanban."""

from __future__ import annotations

import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtWidgets import QMessageBox

from pykanban import board_logic
from pykanban.config import Settings
from pykanban.file_handler import WriteError
from pykanban.models import ParseError, Priority, Project, Status, Task


def slugify(value: str) -> str:
    """Create a filesystem-safe slug from a title.

    Args:
        value: The string to slugify.

    Returns:
        A URL-friendly string safe for file paths
        so user can use markdown linking.
    """
    # TODO:write tests
    # if a callable (e.g a method) is passed, call it to get the value
    if callable(value):
        value = value()

    # ensure we realy have a string now
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    slug = slug.strip("-")
    return slug or "project"


@dataclass
class TaskStore:
    """In-memory store for tasks."""

    tasks_by_id: dict[str, Task] = field(default_factory=dict)

    def get(self, task_id: str) -> Task:
        """Get a task by ID."""
        return self.tasks_by_id[task_id]

    def put(self, task: Task) -> None:
        """Add or update a task."""
        self.tasks_by_id[task.id] = task

    def remove(self, task_id: str) -> None:
        """Remove a task by ID."""
        self.tasks_by_id.pop(task_id, None)

    def all(self) -> list[Task]:
        """Return all tasks."""
        return list(self.tasks_by_id.values())


@dataclass
class ProjectStore:
    """In-memory store for projects."""

    projects_by_id: dict[str, Project] = field(default_factory=dict)
    active_project_id: str | None = None

    def get_active(self) -> Project:
        """Get the active project."""
        # TODO: better to show on error_banner
        if self.active_project_id is None:
            raise KeyError("active_project_id is not set")
        return self.projects_by_id[self.active_project_id]

    def set_active(self, project_id: str) -> None:
        """Set the active project by ID."""
        self.active_project_id = project_id

    def put(self, project: Project) -> None:
        """Add or update a project."""
        self.projects_by_id[project.project_id] = project


@dataclass(frozen=True)
class ConflictWarning:
    """Sync-conflict warning surfaced in the UI."""

    path: Path
    reason: str = "Sync conflict detected"


@dataclass
class BoardView:
    """Board view mapping each status to its ordered tasks."""

    columns: dict[Status, list[Task]]


@dataclass
class ScanResult:
    """Result of scanning a project folder."""

    changed_paths: list[Path]
    deleted_paths: list[Path]
    conflict_paths: list[Path]
    mtime_cache: dict[Path, float]


# TODO: make them pure function?
# TODO: it would be better to raise error_banner for this later
# but mvp is to just raise and error and log it,
# since this is an extremely unlikely edge case
# and we don't want to block users with a non-unique ID error
def generate_task_id(store: TaskStore) -> str:
    """Generate a unique task ID."""
    for _ in range(10):
        task_id = uuid4().hex[:8]
        if task_id not in store.tasks_by_id:
            return task_id

    raise RuntimeError(
        "Failed to generate a unique task ID after 10 attempts."
    )


def generate_project_id(store: ProjectStore) -> str:
    """Generate a unique project ID."""
    for _ in range(10):
        project_id = f"p_{uuid4().hex[:8]}"
        if project_id not in store.projects_by_id:
            return project_id

    # TODO: write tests
    raise RuntimeError(
        "Failed to generate a unique project ID after 10 attempts."
    )


def scan_project_folder(
    project_folder: Path, mtime_cache: dict[Path, float]
) -> ScanResult:
    """Scan a project folder and detect changes.

    Args:
        project_folder: The project folder to scan.
        mtime_cache: Cache of file modification times from the last scan.

    Returns:
        A ScanResult containing lists of changed, deleted, and conflict paths,
        as well as an updated mtime cache.

    """
    previous = mtime_cache or {}
    current: dict[Path, float] = {}
    changed: list[Path] = []

    # TODO: write tests
    for path in project_folder.rglob("*.md"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        current[path] = mtime
        if previous.get(path) != mtime:
            changed.append(path)

    deleted = [path for path in previous if path not in current]
    conflict = list(project_folder.rglob(".sync-conflict-*"))

    return ScanResult(
        changed_paths=changed,
        deleted_paths=deleted,
        conflict_paths=conflict,
        mtime_cache=current,
    )


@dataclass
class AppState:
    """Pure data container for the in-memory application state."""

    tasks: TaskStore
    projects: ProjectStore
    errors: list[ParseError | ConflictWarning]
    settings: Settings
    scan_mtime_cache: dict[Path, float] = field(default_factory=dict)

    @classmethod
    def create(cls, settings: Settings) -> AppState:
        """Create a new AppState with empty stores.

        Args:
            settings: Resolved application settings.

        Returns:
            A new AppState with empty stores and error list.
        """
        return cls(
            tasks=TaskStore(),
            projects=ProjectStore(),
            errors=[],
            settings=settings,
        )


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
        self._insert_into_column(project, status, task_id, position=None)

        try:
            task.write(self._task_path(project, task_id))
            project.write()
        except WriteError as e:
            self.state.errors.append(ParseError(path=e.path, reason=e.reason))

        return task

    def update_task(self, task_id: str, fields: dict) -> Task:
        """Update task fields and persist changes.

        Args:
            task_id: Task ID to update.
            fields: Dict of fields to update.

        Returns:
            Updated task.
        """
        task = self.state.tasks.get(task_id)
        project = self.state.projects.get_active()
        old_path = self._task_path(project, task_id)

        # Extract position and remove it from fields
        position = fields.get("position")
        new_status = fields.get("status", task.status)

        # Extract fields to update
        fields = {
            k: v for k, v in fields.items() if k not in {"position", "status"}
        }

        if new_status != task.status:
            self._move_between_columns(project, task_id, new_status, position)
            task.status = new_status
        elif position is not None:
            self._reorder_in_column(project, task_id, position)

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
            new_path = self._task_path(project, task_id)
            if old_path != new_path and old_path.exists():
                old_path.unlink()

            # Save the task to the new path
            task.write(new_path)
            project.write()
        except WriteError as e:
            self.state.errors.append(ParseError(path=e.path, reason=e.reason))

        return task

    # TODO: edge case handling; if position -1 what happen?
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
        task = self.state.tasks.get(task_id)
        project = self.state.projects.get_active()

        self._move_between_columns(project, task_id, new_status, position)
        task.status = new_status
        task.updated = datetime.now()

        # TODO: write tests
        try:
            task.write(self._task_path(project, task_id))
            project.write()
        except WriteError as e:
            self.state.errors.append(ParseError(path=e.path, reason=e.reason))

        return task

    def delete_task(self, task_id: str) -> None:
        """Delete a task and remove it from the board.

        Args:
            task_id: Task ID to delete.
        """
        task = self.state.tasks.get(task_id)
        project = self.state.projects.get_active()
        path = self._task_path(project, task_id)

        # TODO: write tests
        try:
            path.unlink()
        except OSError as e:
            self.state.errors.append(ParseError(path=path, reason=str(e)))
            return

        self._remove_from_columns(project, task_id)
        self.state.tasks.remove(task_id)

        # TODO: write tests
        try:
            project.write()
        except WriteError as e:
            self.state.errors.append(ParseError(path=e.path, reason=e.reason))

    def _task_path(self, project: Project, task_id: str) -> Path:
        """Build a task file path for a project.

        The filename follows the "title-slug--id.md" pattern.

        Args:
            project: The project to build the path for.
            task_id: The task ID to build the path for.

        Returns:
            The full path to the task file.
        """
        task = self.state.tasks.get(task_id)
        slug = slugify(task.title)
        return project.folder_path / f"{slug}--{task_id}.md"

    def _insert_into_column(
        self,
        project: Project,
        status: Status,
        task_id: str,
        position: int | None,
    ) -> None:
        """Insert a task ID into a column at position."""
        column = project.column_order.setdefault(status.value, [])
        if position is None:
            column.append(task_id)
            return

        position = max(0, min(position, len(column)))
        column.insert(position, task_id)

    def _remove_from_columns(self, project: Project, task_id: str) -> None:
        """Remove a task ID from all columns."""
        for key, ids in project.column_order.items():
            project.column_order[key] = [i for i in ids if i != task_id]

    def _reorder_in_column(
        self, project: Project, task_id: str, position: int
    ) -> None:
        """Reorder a task within its current column."""
        for key, ids in project.column_order.items():
            if task_id in ids:
                ids.remove(task_id)
                position = max(0, min(position, len(ids)))
                ids.insert(position, task_id)
                return

    def _move_between_columns(
        self,
        project: Project,
        task_id: str,
        new_status: Status,
        position: int | None,
    ) -> None:
        """Move a task ID across columns."""
        self._remove_from_columns(project, task_id)
        self._insert_into_column(project, new_status, task_id, position)


class ProjectManager:
    """Responsible for project lifecycle operations: create, switch, delete, archive."""

    def __init__(self, state: AppState):
        """Initialize ProjectManager with application state.

        Args:
            state: The application state to operate on.
        """
        self.state: AppState = state

    def startup_scan(self, projects_dir: Path) -> None:
        """Scan all project folders on startup and populate stores.

        Active projects have their tasks loaded into memory.
        Archived projects have only their metadata loaded, tsks are left
        off-memory intentionally to keep startup fast.

        Args:
            projects_dir: project directory
        """
        self.state.tasks = TaskStore()
        self.state.projects = ProjectStore()
        self.state.errors = []
        self.state.scan_mtime_cache = {}

        # dir may not exist; removed/deleted
        if not projects_dir.exists():
            # recreate the empty directory, so the app doesn't crash
            try:
                projects_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                self.state.errors.append(
                    ParseError(
                        path=projects_dir,
                        reason=f"Failed to create projects directory. Critical permission error: {e}",
                    )
                )
                QMessageBox.critical(
                    None,
                    "Permission Error",
                    f"Failed to create projects directory. Critical permission error: {e}",
                    QMessageBox.Ok,
                )
                sys.exit(1)
            # show error_banner warning that we created empty dir for user
            # but that's uncommon that something probably went wrong
            else:
                self.state.errors.append(
                    ParseError(
                        path=projects_dir,
                        reason="Projects directory not found. Created an empty projects directory. Please check your config, make sure it's pointing to your projects directory, and restart the app.",
                    )
                )
            return

        # collect all folders to scan: top-level projecst + archive sub folder.
        # using a helper keeps the loading logic in one place.
        archive_root = projects_dir / "archive"
        folders_to_scan: list[Path] = []

        for folder in projects_dir.iterdir():
            # skip the archive root itself, its children are handled below
            if folder == archive_root:
                continue

            if folder.is_dir() and (folder / "metadata.yml").exists():
                folders_to_scan.append(folder)

        if archive_root.is_dir():
            for folder in archive_root.iterdir():
                if folder.is_dir() and (folder / "metadata.yml").exists():
                    folders_to_scan.append(folder)

        for folder in folders_to_scan:
            project = Project.from_file(folder / "metadata.yml")
            if isinstance(project, ParseError):
                self.state.errors.append(project)
                continue
            self.state.projects.put(project)

        active = self._choose_active_project()
        # show error_banner if there are no projects found:
        if active is None:
            self.state.errors.append(
                ParseError(
                    path=projects_dir,
                    reason="No projects found. Your projects dir seems deleted by external process. Please check your projects_dir exists and has project folders with metadata.yml files, and restart the app.",
                )
            )
            return

        # load tasks only for non-archived projects to keep memory lean
        for project in self.state.projects.projects_by_id.values():
            if project.archived:
                continue

            # Collect task IDs for this project only
            project_task_ids = self._load_project_tasks(project)
            # Create a temporary task store with just this project's tasks for reconciliation
            project_tasks = TaskStore()
            for task_id in project_task_ids:
                project_tasks.put(self.state.tasks.tasks_by_id[task_id])
            # Reconcile using only this project's tasks
            project.reconcile_order(project_task_ids, project_tasks)

        self.state.projects.set_active(active.project_id)
        # Record conflicts from ALL projects, not just the active one
        self._record_conflicts_all_projects(projects_dir)

    def create_project(self, title: str, description: str) -> Project:
        """Create a new project and persist metadata.

        Args:
            title: Project title.
            description: Project description.

        Returns:
            The created project.
        """
        project_id = generate_project_id(self.state.projects)
        folder = self.state.settings.projects_dir / slugify(title)

        # TODO: implement a dialog or error_banner that show the warning to user
        # prevent same project folder creation with same title
        if folder.exists():
            raise ValueError(
                f"A project folder with the name '{folder.name}' already exists. Please choose a different title."
            )

        # don't use exist_ok=True to avoid accidentally overwriting
        folder.mkdir(parents=True)

        now = datetime.now()
        project = Project(
            project_id=project_id,
            schema=1,
            title=title.strip(),
            description=description.strip(),
            created=now,
            updated=now,
            archived=False,
            column_order=self._empty_column_order(),
            folder_path=folder,
        )

        self.state.projects.put(project)

        # TODO: write tests
        try:
            project.write()
        except WriteError as e:
            self.state.errors.append(ParseError(path=e.path, reason=e.reason))

        return project

    def delete_project(self, project_id: str) -> None:
        """Permanently delete a project folder and remove it from the memory.

        If the deleted project was the active one, the active project is
        reset to None so the board renders and empty state rather than crashing
        on the next get_board() call.

        Args:
            project_id: Project ID to delete.
        """
        project = self.state.projects.projects_by_id[project_id]

        # TODO: write tests
        try:
            shutil.rmtree(str(project.folder_path))
        except OSError as e:
            self.state.errors.append(
                ParseError(path=project.folder_path, reason=str(e))
            )
            return

        # TODO: write tests
        # drop the project and all its tasks from memory
        del self.state.projects.projects_by_id[project_id]
        for task_id in list(self.state.tasks.tasks_by_id):
            if task_id in (
                project.column_order.get(s, []) for s in project.column_order
            ):
                self.state.tasks.remove(task_id)

        # clear active project if it was the one just deleted
        if self.state.projects.active_project_id == project_id:
            self.state.projects.active_project_id = None
            self.state.tasks = TaskStore()

    def archive_project(self, project_id: str) -> None:
        """Archive a project by moving it to archive/.

        The Project object stays in projects_by_id (so the sidebar can
        still show the title under Archived), but if this was the active
        projects its tasks are dropped from memory to avoid holding onto
        data that is no longer needed.

        Args:
            project_id: Project ID to archive.
        """
        project = self.state.projects.projects_by_id[project_id]
        archive_root = self.state.settings.projects_dir / "archive"
        archive_root.mkdir(parents=True, exist_ok=True)

        new_folder = archive_root / project.folder_path.name
        # TODO: write tests
        try:
            shutil.move(str(project.folder_path), str(new_folder))
        except OSError as e:
            self.state.errors.append(
                ParseError(path=project.folder_path, reason=str(e))
            )
            return

        project.folder_path = new_folder
        project.archived = True
        project.updated = datetime.now()

        # TODO: write tests
        try:
            project.write()
        except WriteError as e:
            self.state.errors.append(ParseError(path=e.path, reason=e.reason))

        # free task memory when the archived project was the active one.
        # the projecto object is intentionally kept in projects_by_id
        # so the side bar can still render its title in the archived section
        if self.state.projects.active_project_id == project_id:
            self.state.projects.active_project_id = None
            self.state.tasks = TaskStore()

    def unarchive_project(self, project_id: str) -> None:
        """Unarchive a project by moving it back to projects root.

        Args:
            project_id: Project ID to unarchive.
        """
        project = self.state.projects.projects_by_id[project_id]
        archived_projects = self.state.settings.projects_dir / "archive"
        archived_folder_path = archived_projects / project.folder_path.name
        project_folder_path = (
            self.state.settings.projects_dir / project.folder_path.name
        )

        # TODO: write tests
        try:
            shutil.move(str(archived_folder_path), str(project_folder_path))
        except OSError as e:
            self.state.errors.append(
                ParseError(path=project.folder_path, reason=str(e))
            )
            return

        project.folder_path = project_folder_path
        project.archived = False
        project.updated = datetime.now()

        # TODO: write tests
        try:
            project.write()
        except WriteError as e:
            self.state.errors.append(ParseError(path=e.path, reason=e.reason))

    def switch_project(self, project_id: str) -> BoardView:
        """Switch the active project.

        The caller is responsible for fetching the new
        board view after this returns.

        Args:
            project_id: Project ID to activate.
        """
        project = self.state.projects.projects_by_id[project_id]
        self.state.projects.set_active(project_id)
        self.state.tasks = TaskStore()
        self.state.scan_mtime_cache = {}

        scan = scan_project_folder(
            project.folder_path, self.state.scan_mtime_cache
        )
        self.state.scan_mtime_cache = scan.mtime_cache

        # TODO: write tests
        # Load changed tasks
        for path in scan.changed_paths:
            task = Task.from_file(path)
            if isinstance(task, ParseError):
                self.state.errors.append(task)
                continue
            self.state.tasks.put(task)

        # TODO: write tests, handle edge case
        # Handle deleted tasks
        # Extract task_id from path if possible (for reconciliation)
        # Deleted paths no longer exist, so we just let reconcile_order clean them up
        for path in scan.deleted_paths:
            pass

        project.reconcile_order(
            set(self.state.tasks.tasks_by_id.keys()), self.state.tasks
        )

        # TODO: write tests
        # Record conflicts from scan result
        for path in scan.conflict_paths:
            self.state.errors.append(ConflictWarning(path=path))

    def _choose_active_project(self) -> Project | None:
        """Choose an initial active project."""
        if not self.state.projects.projects_by_id:
            return None

        for project in self.state.projects.projects_by_id.values():
            if not project.archived:
                return project

        # TODO: write tests
        return next(iter(self.state.projects.projects_by_id.values()))

    def _load_project_tasks(self, project: Project) -> set[str]:
        """Load tasks from a project folder and return the set of loaded task IDs.

        Also seeds scan_mtime_cache so the first switch_project call treats
        unchanged files as already seen instead of re-parsing everything.
        """
        project_task_ids: set[str] = set()
        for md_file in project.folder_path.rglob("*.md"):
            task = Task.from_file(md_file)
            if isinstance(task, ParseError):
                self.state.errors.append(task)
                continue
            self.state.tasks.put(task)
            project_task_ids.add(task.id)

            # TODO: write tests
            # seed the mtime cache while we have the file in hand
            try:
                self.state.scan_mtime_cache[md_file] = md_file.stat().st_mtime
            except OSError:
                # file disappeared between rglob and stat; skip silently
                pass
        return project_task_ids

    def _record_conflicts(self, folder: Path) -> None:
        """Record sync-conflict files as warnings."""
        for path in folder.rglob(".sync-conflict-*"):
            self.state.errors.append(ConflictWarning(path=path))

    def _record_conflicts_all_projects(self, projects_dir: Path) -> None:
        """Record sync-conflict files from all projects."""
        for project in self.state.projects.projects_by_id.values():
            self._record_conflicts(project.folder_path)

    def _empty_column_order(self) -> dict[str, list[str]]:
        """Initialize an empty column order."""
        return {
            Status.BACKLOG.value: [],
            Status.TODO.value: [],
            Status.DOING.value: [],
            Status.DONE.value: [],
        }


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
        """Create a new project."""
        return self.projects.create_project(title, description)

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
                Status.BACKLOG: board_logic.get_column(
                    project, Status.BACKLOG, self.state.tasks
                ),
                Status.TODO: board_logic.get_column(
                    project, Status.TODO, self.state.tasks
                ),
                Status.DOING: board_logic.get_column(
                    project, Status.DOING, self.state.tasks
                ),
                Status.DONE: board_logic.get_column(
                    project, Status.DONE, self.state.tasks
                ),
            }
        )
