"""Monitor PyKanban project folders for Markdown file changes.

This module provides a background watcher that detects file creation,
modification, and deletion events. It primarily relies on
QFileSystemWatcher (inotify on Linux) and automatically falls back
to periodic polling when the system watch limit is exceeded.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal

from pykanban.logger import get_logger
from pykanban.models import Project

logger = get_logger(__name__)


class Watcher(QObject):
    """Background watcher that monitors project folders for changes.

    The watcher tracks Markdown files within active project folders and
    notifies consumers when files are added, modified, or deleted.

    Monitoring is performed using QFileSystemWatcher when possible.
    If the operating system's watch limit is reached, the watcher
    falls back to periodic polling based on file modification times.
    """

    # changed: modified or new md files
    # deleted: md files that no longer exist
    changes_detected = Signal(list, list)
    project_folder_deleted = Signal(object)  # pases pathlib.Path

    # poll interval used when file inotify is unavaliable
    _POLL_INTERVAL_MS = 5_000

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._fs_watcher = QFileSystemWatcher(self)

        # timer used only when falling back to polling mode
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self._POLL_INTERVAL_MS)

        # repeat indefinitely until explicitly stopped.
        self._poll_timer.setSingleShot(False)

        self._watched_projects: list[Project] = []

        # stores the last known modification time for each tracked file
        self._mtime_cache: dict[Path, float] = {}

        # indicates whether poll mode is currently active
        self._using_fallback = False

        self._fs_watcher.directoryChanged.connect(self._on_dir_changed)
        self._fs_watcher.fileChanged.connect(self._on_file_changed)
        self._poll_timer.timeout.connect(self._poll_all)

    def set_projects(
        self, projects: list[Project], projects_dir: Path
    ) -> None:
        """Replace the set of projects being monitored.

        Existing file system watches are removed and recreated for
        provided projects.
        """

        # remove all previously registered watches
        if self._fs_watcher.directories():
            self._fs_watcher.removePaths(self._fs_watcher.directories())
        if self._fs_watcher.files():
            self._fs_watcher.removePaths(self._fs_watcher.files())

        self._projects_dir = projects_dir

        # TODO: maybe we could add a logic to check changes for archive root
        # folder without impact memory usage or performance via poll interval?
        #
        # archived projects are excluded because they should not
        # trigger file change notifications
        self._watched_projects = [p for p in projects if not p.archived]

        # reset cached file state before rebuilding watches
        self._mtime_cache = {}

        # watch each project folder for file additions and deletions
        dirs = [str(p.folder_path) for p in self._watched_projects]

        # also watch the parent projects_dir for removal of projects
        dirs.append(str(projects_dir))

        # TODO: can we do folder path detection instead of using
        # rglob everywhere? maybe a pure function that handle it?
        #
        # register every md file so content modifications can be detected
        # directly by the filesystem watcher
        files = [
            str(f)
            for p in self._watched_projects
            for f in p.folder_path.rglob("*.md")
        ]

        logger.debug(
            "Registering watches: %d diretor(ies), %d file(s)",
            len(dirs),
            len(files),
        )

        failed_dirs = self._fs_watcher.addPaths(dirs)
        failed_files = self._fs_watcher.addPaths(files)

        if failed_dirs or failed_files:
            # file system watch register failed, probably because
            # of system inotify limit has been reached
            logger.warning(
                "Failed to register watches: %d diretor(ies), %d file(s)",
                "falling back to polling mode every %d ms",
                len(failed_dirs),
                len(failed_files),
                self._POLL_INTERVAL_MS,
            )

            # seed the cache and switch to polling mode
            self._seed_mtime_cache()

            if not self._using_fallback:
                self._using_fallback = True
                self._poll_timer.start()
        else:
            # file system watching is available again,
            # so remove polling
            self._poll_timer.stop()
            self._using_fallback = False

    def _on_dir_changed(self, path: str) -> None:
        """Handle directory level filesystem events.

        directory notifications are used to detect newly created files,
        deleted files, and removed project folders.
        """
        folder = Path(path)
        logger.debug("Directory changed: %s", path)

        # TODO: find alternative for nested statements
        # check if any project folder disappeared
        if folder == self._projects_dir:
            for project in self._watched_projects:
                if not project.folder_path.exists():
                    self.project_folder_deleted.emit(project.folder_path)
            return

        # ignore notify for dir that no longer exist
        if not folder.exists():
            logger.warning(
                "Ignoring change for non-existent directory: %s", path
            )
            return

        self._scan_folder(folder)

    def _on_file_changed(self, path: str) -> None:
        """Handle file content changes reported by the watcher."""
        p = Path(path)

        # if the file no longer exist, treat it as a deletion event
        if not p.exists():
            logger.debug("File deleted: %s", path)
            self.changes_detected.emit([], [p])
            return

        # re-register the file watch:
        #
        # some platforms remove file watches when a file is deleted
        # and recreated, even if the path remains the same
        self._fs_watcher.addPath(path)

        logger.debug("File modified: %s", path)
        self.changes_detected.emit([p], [])

    def _poll_all(self) -> None:
        """Check all watched projects for changes using modification times.

        This method is used only when file system watchig is unavaliable.
        """
        changed, deleted = [], []

        # TODO: remove nested loop for more easy to read alternative
        for project in self._watched_projects:
            current: dict[Path, float] = {}

            # build a snapshot of current md files and their modify time
            for f in project.folder_path.rglob("*.md"):
                try:
                    # stat(): is file.stat() use os library
                    # st_mtime: file modification timestamp is a float
                    # representing seconds since the unix epoch.
                    mtime = f.stat().st_mtime
                except OSError:
                    # ignore files that become inaccessible while scanning
                    logger.warning("Failed to stat file: %s", f)
                    continue

                # stores dict for current path modification time state
                # example: current[Path("notest.md")] = 17171412099.1
                current[f] = mtime

                # if the current modification time differs from the last known
                # one, the file was probably modified, so append to chaneged
                if self._mtime_cache.get(f) != mtime:
                    changed.append(f)

            # identify cached files that no longer exist within
            # the current project
            for f in list(self._mtime_cache):
                if (
                    f not in current
                    and f.parts[: len(project.folder_path.parts)]
                    == project.folder_path.parts
                ):
                    deleted.append(f)

            # refresh cache entries with the latest snapshot
            self._mtime_cache.update(current)

        # remove deleted files from the cache
        for f in deleted:
            self._mtime_cache.pop(f, None)

        # check are those include any file, emit if any of the list exist
        if changed or deleted:
            logger.debug(
                "Poll detected %d changed and %d deleted file(s)",
                len(changed),
                len(deleted),
            )
            self.changes_detected.emit(changed, deleted)

    def _scan_folder(self, folder: Path) -> None:
        """Used by directoryChanged to find what appeared or disappeared."""
        current = {f for f in folder.rglob("*.md")}

        # cached files that belong to scanned folder
        cached = {f for f in self._mtime_cache if f.is_relative_to(folder)}

        new_or_modified = [
            f for f in current if self._mtime_cache.get(f) != f.stat().st_mtime
        ]
        deleted = list(cached - current)

        # update cache for files that currently exist
        for f in new_or_modified:
            self._mtime_cache[f] = f.stat().st_mtime

        # remove deleted files fromc ache
        for f in deleted:
            self._mtime_cache.pop(f, None)

        # add new files to inotify (they won't be watched yet)
        if new_or_modified:
            self._fs_watcher.addPaths([str(f) for f in new_or_modified])

        if new_or_modified or deleted:
            logger.debug(
                "Folder scan of '%s': %d new/modified, %d deleted",
                folder,
                len(new_or_modified),
                len(deleted),
            )
            self.changes_detected.emit(new_or_modified, deleted)

    def _seed_mtime_cache(self) -> None:
        """Populate the modification time cache for polling mode."""
        for project in self._watched_projects:
            for f in project.folder_path.rglob("*.md"):
                try:
                    self._mtime_cache[f] = f.stat().st_mtime
                except OSError:
                    logger.warning(
                        "Could not stat file during cache init, skipping: %s",
                        f,
                    )
