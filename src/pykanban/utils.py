"""Utility functions for PyKanban."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import uuid4

from ruamel.yaml.comments import CommentedSeq
from ruamel.yaml.scalarstring import SingleQuotedScalarString

if TYPE_CHECKING:
    from pykanban.store import ProjectStore, TaskStore


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


def flow_id_list(ids: list[str]) -> CommentedSeq:
    """Return a flow-style YAML sequence of single-quoted task ID strings.

    Two problems are solved here:
        - Flow style: renders as [id, id] instead of block "- id" lines.
        - Single-quoted strings: prevents ruamel/YAML 1.1 from casting IDs that
        look like numbers (e.g. "0e532197" → float 0.0) back to non-string
        types on the next load.

    Args:
        ids: Task ID strings to wrap.

    Returns:
        A CommentedSeq configured for flow-style output.1
    """
    seq: CommentedSeq = CommentedSeq(
        [SingleQuotedScalarString(i) for i in ids]
    )
    seq.fa.set_flow_style()
    return seq
