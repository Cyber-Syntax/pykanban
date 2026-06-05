"""Unit tests for the Watcher class using real temporary files."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pykanban.watcher import Watcher


@pytest.fixture
def mock_qfs_watcher():
    """Mock QFileSystemWatcher to avoid real file system watching."""
    with patch("pykanban.watcher.QFileSystemWatcher") as mock:
        instance = MagicMock()
        mock.return_value = instance
        # By default, addPaths succeeds (returns empty list)
        instance.addPaths.return_value = []
        yield instance


@pytest.fixture
def mock_qtimer():
    """Mock QTimer to control polling without real timeouts."""
    with patch("pykanban.watcher.QTimer") as mock:
        instance = MagicMock()
        mock.return_value = instance
        yield instance


@pytest.fixture
def watcher(mock_qfs_watcher, mock_qtimer):
    """Create a Watcher instance with mocked Qt dependencies."""
    return Watcher()


@pytest.fixture
def sample_project(tmp_path):
    """Create a real project folder with a mock Project object."""

    def _make(archived=False, folder_name="project1"):
        project_folder = tmp_path / folder_name
        project_folder.mkdir(exist_ok=True)
        project = MagicMock()
        project.archived = archived
        project.folder_path = project_folder
        return project

    return _make


class TestWatcherInitialization:
    def test_initial_state(self, watcher, mock_qtimer, mock_qfs_watcher):
        assert watcher._watched_projects == []
        assert watcher._mtime_cache == {}
        assert watcher._using_fallback is False
        assert watcher._poll_timer is mock_qtimer
        mock_qtimer.setSingleShot.assert_called_once_with(False)
        mock_qfs_watcher.directoryChanged.connect.assert_called_once()
        mock_qfs_watcher.fileChanged.connect.assert_called_once()
        mock_qtimer.timeout.connect.assert_called_once()


class TestSetProjects:
    def test_set_projects_normal(
        self, watcher, sample_project, mock_qfs_watcher, tmp_path
    ):
        p1 = sample_project(archived=False, folder_name="active")
        p2 = sample_project(archived=True, folder_name="archived")
        # Create some .md files in p1
        (p1.folder_path / "note1.md").touch()
        (p1.folder_path / "sub").mkdir()
        (p1.folder_path / "sub" / "note2.md").touch()

        projects_dir = tmp_path
        watcher.set_projects([p1, p2], projects_dir)

        # Archived project excluded
        assert watcher._watched_projects == [p1]

        # Directories added: active project folder + projects_dir
        expected_dirs = [str(p1.folder_path), str(projects_dir)]
        # Files added: all .md files from active project
        expected_files = [
            str(p1.folder_path / "note1.md"),
            str(p1.folder_path / "sub" / "note2.md"),
        ]
        # addPaths called twice: first for dirs, then for files
        calls = mock_qfs_watcher.addPaths.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0] == expected_dirs
        assert set(calls[1][0][0]) == set(expected_files)  # order may vary

        assert watcher._using_fallback is False
        watcher._poll_timer.stop.assert_called_once()
        assert watcher._mtime_cache == {}

    def test_set_projects_fallback(
        self, watcher, sample_project, mock_qfs_watcher, tmp_path
    ):
        p1 = sample_project(archived=False)
        (p1.folder_path / "note.md").touch()

        projects_dir = tmp_path
        # Simulate failure: first addPaths (dirs) fails
        mock_qfs_watcher.addPaths.side_effect = [["/fake/dir"], []]

        watcher.set_projects([p1], projects_dir)

        assert watcher._using_fallback is True
        watcher._poll_timer.start.assert_called_once()
        # Cache should be seeded
        assert len(watcher._mtime_cache) == 1
        assert (p1.folder_path / "note.md") in watcher._mtime_cache

    def test_set_projects_clears_previous_watches(
        self, watcher, sample_project, mock_qfs_watcher, tmp_path
    ):
        # First call with p1
        p1 = sample_project(archived=False)
        watcher.set_projects([p1], tmp_path)

        # Second call with p2
        p2 = sample_project(archived=False, folder_name="project2")
        mock_qfs_watcher.directories.return_value = ["/old/dir"]
        mock_qfs_watcher.files.return_value = ["/old/file"]

        watcher.set_projects([p2], tmp_path)

        # Old watches removed
        mock_qfs_watcher.removePaths.assert_any_call(["/old/dir"])
        mock_qfs_watcher.removePaths.assert_any_call(["/old/file"])
        # New watches added for p2
        expected_dirs = [str(p2.folder_path), str(tmp_path)]
        # The last call to addPaths should be for files (empty list since no .md files)
        # So we check that addPaths was called with expected_dirs at some point
        mock_qfs_watcher.addPaths.assert_any_call(expected_dirs)


class TestDirectoryChanged:
    def test_project_folder_deleted(self, watcher, sample_project, tmp_path):
        projects_dir = tmp_path
        watcher._projects_dir = projects_dir
        p1 = sample_project(archived=False, folder_name="deleted_project")
        watcher._watched_projects = [p1]
        # Delete the folder
        p1.folder_path.rmdir()

        mock_signal = MagicMock()
        watcher.project_folder_deleted.connect(mock_signal)

        watcher._on_dir_changed(str(projects_dir))

        mock_signal.assert_called_once_with(p1.folder_path)

    def test_ignore_non_project_dir_changes(
        self, watcher, sample_project, tmp_path
    ):
        p1 = sample_project(archived=False)
        watcher._watched_projects = [p1]
        watcher._projects_dir = tmp_path
        subfolder = p1.folder_path / "sub"
        subfolder.mkdir()

        with patch.object(watcher, "_scan_folder") as mock_scan:
            watcher._on_dir_changed(str(subfolder))
            # _scan_folder should be called with a Path object equal to subfolder
            mock_scan.assert_called_once()
            called_path = mock_scan.call_args[0][0]
            assert called_path == subfolder

    def test_ignore_nonexistent_directory(self, watcher):
        watcher._projects_dir = Path("/fake/projects")
        fake_path = Path("/gone")
        # This should not raise any exception or emit signals
        watcher._on_dir_changed(str(fake_path))


class TestFileChanged:
    def test_file_deleted(self, watcher, tmp_path):
        file_path = tmp_path / "deleted.md"
        file_path.touch()
        # Simulate deletion
        file_path.unlink()

        mock_signal = MagicMock()
        watcher.changes_detected.connect(mock_signal)

        watcher._on_file_changed(str(file_path))

        # Signal emitted with empty changed, and the file path in deleted
        mock_signal.assert_called_once_with([], [file_path])

    def test_file_modified(self, watcher, mock_qfs_watcher, tmp_path):
        file_path = tmp_path / "modified.md"
        file_path.touch()

        mock_signal = MagicMock()
        watcher.changes_detected.connect(mock_signal)

        watcher._on_file_changed(str(file_path))

        mock_signal.assert_called_once_with([file_path], [])
        mock_qfs_watcher.addPath.assert_called_once_with(str(file_path))


class TestPollAll:
    def test_no_changes(self, watcher, sample_project):
        p = sample_project(archived=False)
        md_file = p.folder_path / "note.md"
        md_file.touch()
        mtime = md_file.stat().st_mtime
        watcher._watched_projects = [p]
        watcher._mtime_cache = {md_file: mtime}

        mock_signal = MagicMock()
        watcher.changes_detected.connect(mock_signal)

        watcher._poll_all()

        mock_signal.assert_not_called()
        assert watcher._mtime_cache[md_file] == mtime

    def test_new_and_modified_files(self, watcher, sample_project):
        """Use approximate comparison for mtime due to floating point."""
        p = sample_project(archived=False)
        old_file = p.folder_path / "old.md"
        new_file = p.folder_path / "new.md"
        old_file.touch()
        new_file.touch()
        old_mtime = old_file.stat().st_mtime
        # Simulate modification by touching again after a short delay (or just set mtime)
        old_file.touch()
        new_mtime = new_file.stat().st_mtime

        watcher._watched_projects = [p]
        watcher._mtime_cache = {old_file: old_mtime}  # old mtime cached

        mock_signal = MagicMock()
        watcher.changes_detected.connect(mock_signal)

        watcher._poll_all()

        changed, deleted = mock_signal.call_args[0]
        # Both files are considered changed (old modified, new added)
        assert set(changed) == {old_file, new_file}
        assert deleted == []

        # use approximate comparison
        assert watcher._mtime_cache[old_file] == pytest.approx(new_mtime)

    def test_deleted_files(self, watcher, sample_project):
        p = sample_project(archived=False)
        missing_file = p.folder_path / "missing.md"
        missing_file.touch()
        watcher._mtime_cache = {missing_file: 12345.0}
        # Delete the file
        missing_file.unlink()

        watcher._watched_projects = [p]
        # rglob will not return missing_file
        mock_signal = MagicMock()
        watcher.changes_detected.connect(mock_signal)

        watcher._poll_all()

        changed, deleted = mock_signal.call_args[0]
        assert changed == []
        assert deleted == [missing_file]
        assert missing_file not in watcher._mtime_cache

    def test_oserror_ignored(self, watcher, sample_project):
        """Mock state to raise OSError for bad_file."""
        p = sample_project(archived=False)
        bad_file = p.folder_path / "bad.md"
        good_file = p.folder_path / "good.md"
        good_file.touch()
        bad_file.touch()
        # Create bad file but make it unreadable (e.g., remove permissions)
        bad_file.chmod(0o000)

        original_stat = Path.stat

        def stat_side_effect(self):
            if self == bad_file:
                raise OSError("Permission denied")
            return original_stat(self)

        # mock stat for bad_file to raise OSError
        with patch.object(Path, "stat", new=stat_side_effect):
            watcher._watched_projects = [p]
            watcher._mtime_cache = {}

            mock_signal = MagicMock()
            watcher.changes_detected.connect(mock_signal)

            watcher._poll_all()

            changed, deleted = mock_signal.call_args[0]
            assert changed == [good_file]
            assert deleted == []
            assert good_file in watcher._mtime_cache
            assert bad_file not in watcher._mtime_cache


class TestScanFolder:
    def test_new_and_deleted_files(self, watcher, mock_qfs_watcher, tmp_path):
        folder = tmp_path / "scan_folder"
        folder.mkdir()
        existing_file = folder / "existing.md"
        new_file = folder / "new.md"
        existing_file.touch()
        new_file.touch()

        # Simulate cache with older mtime for existing_file and a deleted file
        deleted_file = folder / "deleted.md"
        deleted_file.touch()
        old_mtime = existing_file.stat().st_mtime

        # Modify existing_file
        existing_file.touch()
        new_mtime = existing_file.stat().st_mtime
        watcher._mtime_cache = {existing_file: old_mtime, deleted_file: 300.0}

        # Delete the deleted_file
        deleted_file.unlink()

        mock_signal = MagicMock()
        watcher.changes_detected.connect(mock_signal)

        watcher._scan_folder(folder)

        # existing_file modified, new_file added, deleted_file removed
        mock_signal.assert_called_once()
        changed, deleted = mock_signal.call_args[0]
        assert set(changed) == {existing_file, new_file}
        assert deleted == [deleted_file]
        assert watcher._mtime_cache[existing_file] == new_mtime
        assert watcher._mtime_cache[new_file] == new_file.stat().st_mtime
        assert deleted_file not in watcher._mtime_cache

        # check addPaths called with the two files, order doesn't matter
        actual_files = mock_qfs_watcher.addPaths.call_args[0][0]
        expected_files = [str(new_file), str(existing_file)]
        assert set(actual_files) == set(expected_files)

    def test_no_changes(self, watcher, tmp_path):
        folder = tmp_path / "no_changes"
        folder.mkdir()
        f = folder / "file.md"
        f.touch()
        mtime = f.stat().st_mtime
        watcher._mtime_cache = {f: mtime}

        mock_signal = MagicMock()
        watcher.changes_detected.connect(mock_signal)

        watcher._scan_folder(folder)

        mock_signal.assert_not_called()


class TestSeedMtimeCache:
    def test_seed_populates_cache(self, watcher, sample_project):
        p1 = sample_project(archived=False, folder_name="p1")
        p2 = sample_project(archived=False, folder_name="p2")
        f1 = p1.folder_path / "a.md"
        f2 = p2.folder_path / "b.md"
        f1.touch()
        f2.touch()
        watcher._watched_projects = [p1, p2]

        watcher._seed_mtime_cache()

        assert len(watcher._mtime_cache) == 2
        assert watcher._mtime_cache[f1] == f1.stat().st_mtime
        assert watcher._mtime_cache[f2] == f2.stat().st_mtime

    def test_skips_inaccessible_files(self, watcher, sample_project):
        p = sample_project(archived=False)
        good = p.folder_path / "good.md"
        bad = p.folder_path / "bad.md"
        good.touch()
        bad.touch()
        bad.chmod(0o000)  # doesn not affect stat, kept for clarity

        original_stat = Path.stat

        def stat_side_effect(self):
            if self == bad:
                raise OSError("Permission denied")
            return original_stat(self)

        # mock stat for bad file to raise OSError
        with patch.object(Path, "stat", new=stat_side_effect):
            watcher._watched_projects = [p]
            watcher._seed_mtime_cache()

            assert good in watcher._mtime_cache
            assert bad not in watcher._mtime_cache


class TestSignals:
    def test_changes_detected_emitted_from_dir_change(self, watcher, tmp_path):
        folder = tmp_path / "signal_test"
        folder.mkdir()
        new_file = folder / "new.md"
        new_file.touch()
        watcher._mtime_cache = {}

        mock_signal = MagicMock()
        watcher.changes_detected.connect(mock_signal)

        watcher._scan_folder(folder)

        mock_signal.assert_called_once_with([new_file], [])

    def test_project_folder_deleted_emitted(
        self, watcher, sample_project, tmp_path
    ):
        watcher._projects_dir = tmp_path
        p = sample_project(archived=False)
        watcher._watched_projects = [p]
        # Delete project folder
        p.folder_path.rmdir()

        mock_signal = MagicMock()
        watcher.project_folder_deleted.connect(mock_signal)

        watcher._on_dir_changed(str(tmp_path))

        mock_signal.assert_called_once_with(p.folder_path)
