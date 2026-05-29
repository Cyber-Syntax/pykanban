"""Unit tests for pykanban.file_handler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from pykanban.file_handler import WriteError, atomic_write


class TestAtomicWrite:
    """Unit tests for file_handler.atomic_write."""

    def test_writes_content_to_destination(self, tmp_path: Path) -> None:
        """Creates the file with the exact content supplied."""
        target = tmp_path / "output.md"
        atomic_write(target, "hello world")
        assert target.read_text(encoding="utf-8") == "hello world"

    def test_creates_intermediate_directories(self, tmp_path: Path) -> None:
        """Automatically creates missing parent directories."""
        target = tmp_path / "a" / "b" / "c" / "file.md"
        atomic_write(target, "nested")
        assert target.exists()

    def test_no_tmp_file_left_after_success(self, tmp_path: Path) -> None:
        """The .tmp artefact is removed after a successful write."""
        target = tmp_path / "output.md"
        atomic_write(target, "data")
        assert not (tmp_path / "output.md.tmp").exists()

    def test_raises_write_error_on_os_failure(self, tmp_path: Path) -> None:
        """Converts an OSError into a WriteError."""
        target = tmp_path / "output.md"
        with (
            patch(
                "pykanban.file_handler.os.fsync",
                side_effect=OSError("disk full"),
            ),
            pytest.raises(WriteError),
        ):
            atomic_write(target, "data")

    def test_cleans_up_tmp_file_on_failure(self, tmp_path: Path) -> None:
        """Removes the .tmp file even when the write fails."""
        target = tmp_path / "output.md"
        with (
            patch(
                "pykanban.file_handler.os.fsync", side_effect=OSError("boom")
            ),
            pytest.raises(WriteError),
        ):
            atomic_write(target, "data")
        assert not (tmp_path / "output.md.tmp").exists()

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        """Replaces stale content atomically."""
        target = tmp_path / "output.md"
        target.write_text("old content")
        atomic_write(target, "new content")
        assert target.read_text() == "new content"


class TestWriteError:
    """Unit tests for file_handler.WriteError."""

    def test_is_an_exception_subclass(self) -> None:
        assert isinstance(WriteError(path=Path("/p"), reason="x"), Exception)

    def test_stores_path_and_reason(self) -> None:
        p = Path("/some/file.md")
        err = WriteError(path=p, reason="disk full")
        assert err.path == p
        assert err.reason == "disk full"
