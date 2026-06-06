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
from pykanban.logger import get_logger
from pykanban.models import Project
from pykanban.parser import parse_project, parse_task, write_project
from pykanban.project_utils import (
    choose_active_project,
    empty_column_order,
    find_all_project_conflicts,
    load_project_tasks,
    reconcile_order,
)
from pykanban.store import BoardView, ProjectStore, TaskStore
from pykanban.task_utils import (
    build_task_file_path,
    insert_into_column,
    remove_from_columns,
)
from pykanban.utils import generate_project_id, slugify

if TYPE_CHECKING:
    from pykanban.state import AppState

logger = get_logger(__name__)


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
    previous: dict[Path, float] = mtime_cache or {}
    current: dict[Path, float] = {}
    changed: list[Path] = []

    # TODO: write tests
    logger.debug("Scanning project folder: %s", project_folder)
    for path in project_folder.rglob("*.md"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            # a single file that can't be accessed shouldn't prevent
            # the whole scan (e.g. a sync tool that locked the file that would
            # be fine a moment later). Best effort: log the error and continue.
            logger.warning(
                "Could not stat file %s, skipping %s", path, exc_info=True
            )
            continue
        current[path] = mtime
        if previous.get(path) != mtime:
            logger.debug("Changed file: %s", path)
            changed.append(path)

    deleted = [path for path in previous if path not in current]
    conflict = list(project_folder.rglob(".sync-conflict-*"))

    logger.info(
        "Scan completed: %d changed, %d deleted, %d conflict",
        len(changed),
        len(deleted),
        len(conflict),
    )

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

    # TODO: too many branches, refactor with helper functions
    def startup_scan(self, projects_dir: Path) -> None:
        """Scan all project folders on startup and populate stores.

        Active projects have their tasks loaded into memory.
        Archived projects have only their metadata loaded, tsks are left
        off-memory intentionally to keep startup fast.

        Args:
            projects_dir: project directory
        """
        logger.debug("Startup scan for projects directory: %s", projects_dir)

        self.state.tasks = TaskStore()
        self.state.projects = ProjectStore()
        self.state.errors = []
        self.state.scan_mtime_cache = {}

        # dir may not exist; removed/deleted
        if not projects_dir.exists():
            logger.warning(
                "Projects directory does not exist: %s", projects_dir
            )
            logger.warning("Creating projects directory: %s", projects_dir)
            # recreate the empty directory, so the app doesn't crash
            try:
                projects_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.exception(
                    "Failed to create projects directory: %s", projects_dir
                )
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
                logger.warning(
                    "Projects directory not found. Created an empty projects directory: %s",
                    projects_dir,
                )
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
            project = parse_project(folder / "metadata.yml")
            if isinstance(project, ParseError):
                self.state.errors.append(project)
                continue
            self.state.projects.put(project)

        active = choose_active_project(self.state.projects.projects_by_id)
        # show error_banner if there are no projects found:
        if active is None:
            logger.warning("No active project found")
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
            project.column_order = reconcile_order(
                project.column_order,
                load_result.loaded_task_ids,
                project_tasks.tasks_by_id,
            )

        logger.info("Loaded %d projects folders", len(folders_to_scan))

        logger.debug("Active project: %s", active.project_id)
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
        logger.debug("Creating project: %s", title)
        project_id = generate_project_id(self.state.projects)
        folder = self.state.settings.projects_dir / slugify(title)

        # TODO: implement a dialog or error_banner that show the warning to user
        # prevent same project folder creation with same title
        if folder.exists():
            logger.warning("Project folder already exists: %s", folder)
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

        logger.info("Project created: %s", project_id)
        # TODO: write tests
        try:
            write_project(project)
        except WriteError as e:
            logger.exception("Failed to write project: %s", project_id)
            self.state.errors.append(ParseError(path=e.path, reason=e.reason))

        return project

    # TODO: write tests
    def rename_project(self, project_id: str, new_title: str) -> None:
        """Rename a project by changing its title and folder name.

        Args:
            project_id: Project ID to rename.
            new_title: New title for the project.
        """
        logger.debug("Renaming project: %s -> %s", project_id, new_title)
        project = self.state.projects.projects_by_id[project_id]
        old_folder = project.folder_path
        new_folder = old_folder.parent / slugify(new_title)

        # prevent same project folder creation with same title
        if new_folder.exists():
            logger.warning("Folder already exists: %s", new_folder)
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
            logger.exception("Failed to move folder: %s", old_folder)
            self.state.errors.append(
                ParseError(path=old_folder, reason=str(e))
            )
            return

        logger.info("Renamed project: %s -> %s", old_folder, new_folder)
        project.folder_path = new_folder
        project.title = new_title.strip()
        project.updated = datetime.now()

        try:
            write_project(project)
        except WriteError as e:
            logger.exception("Failed to write project: %s", project_id)
            self.state.errors.append(ParseError(path=e.path, reason=e.reason))

        logger.info("Updated project: %s", project_id)

    def delete_project(self, project_id: str) -> None:
        """Permanently delete a project folder and remove it from the memory.

        If the deleted project was the active one, choose another non-archived
        project to activate and load its tasks. If switching to the replacement
        fails, record an error and fall back to an empty state.

        Args:
            project_id: Project ID to delete.
        """
        logger.debug("Deleting project: %s", project_id)
        project = self.state.projects.projects_by_id.get(project_id)
        if project is None:
            return

        try:
            shutil.rmtree(str(project.folder_path))
        except OSError as e:
            logger.exception(
                "Failed to delete folder: %s", project.folder_path
            )
            self.state.errors.append(
                ParseError(path=project.folder_path, reason=str(e))
            )
            return

        # remove the project from memory
        del self.state.projects.projects_by_id[project_id]

        # if deleted project wasn't active, nothing else to do
        if self.state.projects.active_project_id != project_id:
            return

        logger.debug("Finding replacement for deleted project: %s", project_id)
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
                logger.exception(
                    "Failed to switch to replacement project: %s",
                    replacement.project_id,
                )
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
            logger.info(
                "Switched to replacement project: %s", replacement.project_id
            )
        else:
            logger.info("No replacement project found for: %s", project_id)
            # no non-archived projects left — clear active and tasks
            self.state.projects.active_project_id = None
            self.state.tasks.tasks_by_id.clear()

        logger.info("Deleted project: %s", project_id)
        logger.debug(
            "Deleted project cleared from memory: %s, active_project_id=%s",
            project_id,
            self.state.projects.active_project_id,
        )

    def archive_project(self, project_id: str) -> None:
        """Archive a project by moving it to archive/.

        The Project object stays in projects_by_id (so the sidebar can
        still show the title under Archived), but if this was the active
        projects its tasks are dropped from memory to avoid holding onto
        data that is no longer needed.

        Args:
            project_id: Project ID to archive.
        """
        logger.debug("Archiving project: %s", project_id)
        project = self.state.projects.projects_by_id[project_id]
        archive_root = self.state.settings.projects_dir / "archive"
        archive_root.mkdir(parents=True, exist_ok=True)

        new_folder = archive_root / project.folder_path.name
        try:
            shutil.move(str(project.folder_path), str(new_folder))
        except OSError as e:
            logger.exception("Failed to move folder: %s", project.folder_path)
            self.state.errors.append(
                ParseError(path=project.folder_path, reason=str(e))
            )
            return

        project.folder_path = new_folder
        project.archived = True
        project.updated = datetime.now()

        try:
            write_project(project)
        except WriteError as e:
            logger.exception("Failed to write project: %s", e.path)
            self.state.errors.append(ParseError(path=e.path, reason=e.reason))

        # free task memory when the archived project was the active one.
        # the project object is intentionally kept in projects_by_id
        # so the side bar can still render its title in the archived section
        if self.state.projects.active_project_id == project_id:
            self.state.projects.active_project_id = None
            self.state.tasks = TaskStore()

        logger.info("Archived project: %s", project_id)
        logger.debug(
            "Archived project cleared from memory: %s, active_project_id=%s",
            project_id,
            self.state.projects.active_project_id,
        )

    def unarchive_project(self, project_id: str) -> None:
        """Unarchive a project by moving it back to projects root.

        Args:
            project_id: Project ID to unarchive.
        """
        logger.debug("Unarchiving project: %s", project_id)
        project = self.state.projects.projects_by_id[project_id]
        archived_projects = self.state.settings.projects_dir / "archive"
        archived_folder_path = archived_projects / project.folder_path.name
        project_folder_path = (
            self.state.settings.projects_dir / project.folder_path.name
        )

        try:
            shutil.move(str(archived_folder_path), str(project_folder_path))
        except OSError as e:
            logger.exception("Failed to move folder: %s", archived_folder_path)
            self.state.errors.append(
                ParseError(path=project.folder_path, reason=str(e))
            )
            return

        project.folder_path = project_folder_path
        project.archived = False
        project.updated = datetime.now()

        try:
            write_project(project)
        except WriteError as e:
            logger.exception("Failed to write project: %s", e.path)
            self.state.errors.append(ParseError(path=e.path, reason=e.reason))

        logger.info("Unarchived project: %s", project_id)

    def switch_project(self, project_id: str) -> BoardView:
        """Switch the active project.

        The caller is responsible for fetching the new
        board view after this returns.

        Args:
            project_id: Project ID to activate.
        """
        logger.debug("Switching project: %s", project_id)
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
            task = parse_task(path)
            if isinstance(task, ParseError):
                logger.error("Failed to parse task %s: %s", path, task.reason)
                self.state.errors.append(task)
                continue
            self.state.tasks.put(task)

        # Handle deleted tasks
        # Extract task_id from path if possible (for reconciliation)
        # Deleted paths no longer exist, so we just let reconcile_order clean them up
        for path in scan.deleted_paths:
            logger.debug(
                "Deleted task - will be cleaned up by reconcile_order - %s",
                path,
            )

        project.column_order = reconcile_order(
            project.column_order,
            set(self.state.tasks.tasks_by_id.keys()),
            self.state.tasks.tasks_by_id,
        )

        # Record conflicts from scan result
        for path in scan.conflict_paths:
            logger.debug("Conflict path: %s", path)
            self.state.errors.append(ConflictWarning(path=path))

        logger.debug(
            "Switched project: project_id=%s, active_project_id=%s",
            project_id,
            self.state.projects.active_project_id,
        )

    def apply_external_changes(
        self, changed: list[Path], deleted: list[Path]
    ) -> None:
        """Apply external detected file changes to in memory state.

        Called by MainWindow when Watcher fires.
        Errors are append to state.errors (shown by error_banner)
        Does not write any files, read-only reaction to external changes.

        Args:
            changed: md files that are new or modified
            deleted: md files that no longer exist on disk
        """
        logger.debug(
            "Apply external changes: changed=%s, deleted=%s",
            len(changed),
            len(deleted),
        )
        # may raise if no active
        active = self.state.projects.get_active()

        # re-parse changed/new files
        for path in changed:
            task = parse_task(path)
            if isinstance(task, ParseError):
                logger.warning("Parse error: %s", task)
                self.state.errors.append(task)
                continue

            # remove task from column order if status changed
            old_task = self.state.tasks.tasks_by_id.get(task.id)
            if old_task is not None and old_task.status != task.status:
                logger.debug(
                    "Status changed: old=%s, new=%s",
                    old_task.status,
                    task.status,
                )
                active.column_order = remove_from_columns(
                    active.column_order, task.id
                )
                active.column_order = insert_into_column(
                    active.column_order, task.status.value, task.id
                )
            else:
                logger.debug(
                    "Task re-parse without status unchanged: %s", task.id
                )

            # add/update task in memory
            self.state.tasks.put(task)

        logger.debug(
            "Applied external changes: changed=%s, deleted=%s",
            len(changed),
            len(deleted),
        )

        # TODO: this is so nested and hard to read, refactor to better flat structure
        deleted_ids: set[str] = set()
        for path in deleted:
            # match by path -> task id(filename pattern: slug--id.md)
            stem = path.stem  # e.g "learn-pykanban--a3f9c1b2"
            if "--" not in stem:
                logger.debug("Skipping task: %s", stem)
                continue

            task_id = stem.rsplit("--", 1)[-1]
            task = self.state.tasks.tasks_by_id.get(task_id)

            if task is not None:
                logger.debug("Found task: %s", task_id)
                # task still exist in memory. check whether its current
                # expected path differs from the deleted path -- if so,
                # this deletion was caused by an internal rename (TaskManager
                # wrote a new file and unlinked the old one).
                # Treat it as a no-op; the watcher will emit a separate
                # changed event for the new file which apply_external_changes
                # will handle above.
                expected_path = build_task_file_path(
                    active.folder_path, task.title, task_id
                )
                if expected_path != path:
                    logger.debug(
                        "Expected path mismatch: expected=%s, actual=%s",
                        expected_path,
                        path,
                    )
                    continue
                # expected path matches deleted path: the file is truly gone
                # externally (not a rename), so remove it from memory.
                self.state.tasks.remove(task_id)
                deleted_ids.add(task_id)
                self.state.errors.append(
                    ParseError(path=path, reason="File deleted externally")
                )
                logger.info("Deleted task: %s", path)

        logger.debug(
            "Reconciling column order after external deletions: deleted_ids=%s",
            deleted_ids,
        )
        # reconcile column order (drops stale IDs, re-places orphans)
        if deleted_ids:
            active.column_order = reconcile_order(
                active.column_order,
                set(self.state.tasks.tasks_by_id.keys()),
                self.state.tasks.tasks_by_id,
            )
        else:
            logger.debug(
                "No deleted IDs, skipping column order reconciliation."
            )

    def handle_project_folder_deleted(self, folder_path: Path) -> None:
        """Record an error when an entire project folder is removed externally.

        Args:
            folder_path: folder that no longer exists on disk.
        """
        logger.debug(
            "Project folder deleted externally: folder_path=%s",
            folder_path,
        )
        project = next(
            (
                p
                for p in self.state.projects.projects_by_id.values()
                if p.folder_path == folder_path
            ),
            None,
        )
        if project is None:
            logger.debug(
                "No project found for deleted folder: folder_path=%s",
                folder_path,
            )
            return

        self.state.errors.append(
            ParseError(
                path=folder_path,
                reason=f"Project folder '{project.title}' was deleted externally.",
            )
        )

        logger.debug(
            "Project removed externally, so we remove it from memory: project_id=%s",
            project.project_id,
        )
        # remove from memory so sidebar no longer shows it
        del self.state.projects.projects_by_id[project.project_id]

        # if it was active, clear active state and tasks
        if self.state.projects.active_project_id == project.project_id:
            logger.debug(
                "Project was active, clearing active state and tasks: project_id=%s",
                project.project_id,
            )
            self.state.projects.active_project_id = None
            self.state.tasks = TaskStore()
        else:
            logger.debug(
                "Project was not active, no need to clear active state and tasks: project_id=%s",
                project.project_id,
            )
