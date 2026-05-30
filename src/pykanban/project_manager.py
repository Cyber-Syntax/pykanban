"""ProjectManager handles project lifecycle operations: create, switch..."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from pykanban.error import ConflictWarning, ParseError
from pykanban.exceptions import WriteError
from pykanban.models import Project, Task
from pykanban.project_utils import (
    choose_active_project,
    empty_column_order,
    find_all_project_conflicts,
    load_project_tasks,
)
from pykanban.store import BoardView, ProjectStore, TaskStore
from pykanban.utils import generate_project_id, slugify

if TYPE_CHECKING:
    from pykanban.state import AppState


@dataclass
class ScanResult:
    """Result of scanning a project folder."""

    changed_paths: list[Path]
    deleted_paths: list[Path]
    conflict_paths: list[Path]
    mtime_cache: dict[Path, float]


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

        active = choose_active_project(self.state.projects.projects_by_id)
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
            load_result = load_project_tasks(
                project, self.state.scan_mtime_cache
            )
            self.state.scan_mtime_cache = load_result.updated_mtime_cache
            self.state.errors.extend(load_result.parse_errors)

            # Create a temporary task store with just this project's tasks for reconciliation
            project_tasks = TaskStore()
            for task in load_result.loaded_tasks:
                # add to main store
                self.state.tasks.put(task)
                # add to temp project store for reconcile_order
                project_tasks.put(task)

            # Reconcile using only this project's tasks
            project.reconcile_order(load_result.loaded_task_ids, project_tasks)

        self.state.projects.set_active(active.project_id)
        # Record conflicts from ALL projects, not just the active one
        conflicts = find_all_project_conflicts(
            self.state.projects.projects_by_id
        )
        self.state.errors.extend(conflicts)

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
            column_order=empty_column_order(),
            folder_path=folder,
        )

        self.state.projects.put(project)

        # TODO: write tests
        try:
            project.write()
        except WriteError as e:
            self.state.errors.append(ParseError(path=e.path, reason=e.reason))

        return project

    # TODO: write tests
    def rename_project(self, project_id: str, new_title: str) -> None:
        """Rename a project by changing its title and folder name.

        Args:
            project_id: Project ID to rename.
            new_title: New title for the project.
        """
        project = self.state.projects.projects_by_id[project_id]
        old_folder = project.folder_path
        new_folder = old_folder.parent / slugify(new_title)

        # prevent same project folder creation with same title
        if new_folder.exists():
            self.state.errors.append(
                ParseError(
                    path=new_folder,
                    reason=f"A project folder with the name '{new_folder.name}' already exists. Please choose a different title.",
                )
            )
            return

        try:
            shutil.move(str(old_folder), str(new_folder))
        except OSError as e:
            self.state.errors.append(
                ParseError(path=old_folder, reason=str(e))
            )
            return

        project.folder_path = new_folder
        project.title = new_title.strip()
        project.updated = datetime.now()

        try:
            project.write()
        except WriteError as e:
            self.state.errors.append(ParseError(path=e.path, reason=e.reason))

    def delete_project(self, project_id: str) -> None:
        """Permanently delete a project folder and remove it from the memory.

        If the deleted project was the active one, choose another non-archived
        project to activate and load its tasks. If switching to the replacement
        fails, record an error and fall back to an empty state.

        Args:
            project_id: Project ID to delete.
        """
        project = self.state.projects.projects_by_id.get(project_id)
        if project is None:
            return

        try:
            shutil.rmtree(str(project.folder_path))
        except OSError as e:
            self.state.errors.append(
                ParseError(path=project.folder_path, reason=str(e))
            )
            return

        # remove the project from memory
        del self.state.projects.projects_by_id[project_id]

        # if deleted project wasn't active, nothing else to do
        if self.state.projects.active_project_id != project_id:
            return

        # find a non-archived replacement project
        replacement = None
        for p in self.state.projects.projects_by_id.values():
            if not p.archived:
                replacement = p
                break

        if replacement is not None:
            try:
                # Attempt to switch to the replacement (this may raise)
                self.switch_project(replacement.project_id)
            except Exception as e:
                # Record the failure for the UI and clear state to a safe empty state
                self.state.errors.append(
                    ParseError(
                        path=replacement.folder_path,
                        reason=(
                            f"Projects deleted was active. Failed to switch to replacement "
                            f"project '{replacement.title}'. Error: {e}"
                        ),
                    )
                )
                self.state.projects.active_project_id = None
                self.state.tasks.tasks_by_id.clear()
        else:
            # no non-archived projects left — clear active and tasks
            self.state.projects.active_project_id = None
            self.state.tasks.tasks_by_id.clear()

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

        # Load changed tasks
        for path in scan.changed_paths:
            task = Task.from_file(path)
            if isinstance(task, ParseError):
                self.state.errors.append(task)
                continue
            self.state.tasks.put(task)

        # Handle deleted tasks
        # Extract task_id from path if possible (for reconciliation)
        # Deleted paths no longer exist, so we just let reconcile_order clean them up
        for path in scan.deleted_paths:
            pass

        project.reconcile_order(
            set(self.state.tasks.tasks_by_id.keys()), self.state.tasks
        )

        # Record conflicts from scan result
        for path in scan.conflict_paths:
            self.state.errors.append(ConflictWarning(path=path))
