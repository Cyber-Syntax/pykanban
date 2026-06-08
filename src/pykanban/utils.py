"""Utility functions for PyKanban."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import uuid4

from ruamel.yaml.comments import CommentedSeq
from ruamel.yaml.scalarstring import SingleQuotedScalarString

from pykanban.logger import get_logger

if TYPE_CHECKING:
    from pykanban.store import ProjectStore, TaskStore

logger = get_logger(__name__)


# TODO: make them pure function?
# TODO: it would be better to raise error_banner for this later
# but mvp is to just raise and error and log it,
# since this is an extremely unlikely edge case
# and we don't want to block users with a non-unique ID error
def generate_task_id(store: TaskStore) -> str:
    """Generate a unique task ID."""
    for attempt in range(10):
        task_id = uuid4().hex[:8]
        if task_id not in store.tasks_by_id:
            logger.debug(
                "Generated unique task ID: %s (attempt %d)",
                task_id,
                attempt + 1,
            )
            return task_id
        logger.warning(
            "Task ID %s already exists, retrying... attempt %d",
            task_id,
            attempt + 1,
        )

    error_msg = "Failed to generate a unique task ID after 10 attempts."
    logger.error(error_msg)
    raise RuntimeError(error_msg)


def generate_project_id(store: ProjectStore) -> str:
    """Generate a unique project ID."""
    for attempt in range(10):
        project_id = f"p_{uuid4().hex[:8]}"
        if project_id not in store.projects_by_id:
            logger.debug(
                "Generated unique project ID: %s (attempt %d)",
                project_id,
                attempt + 1,
            )
            return project_id
        logger.warning(
            "Project ID %s already exists, retrying... attempt %d",
            project_id,
            attempt + 1,
        )

    error_msg = "Failed to generate a unique project ID after 10 attempts."
    logger.error(error_msg)
    raise RuntimeError(error_msg)


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
        logger.debug("Slugify callable value: %s", value)

    original_value = value
    # ensure we realy have a string now
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    slug = slug.strip("-")
    result = slug or "project"

    if result != original_value:
        logger.debug(
            "Slugify result: %s (original: %s)", result, original_value
        )
    else:
        logger.debug("Slugify result: %s (no change)", result)

    return result


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
    logger.debug("Converting IDs to flow-style YAML: ids=%s", ids)
    seq: CommentedSeq = CommentedSeq(
        [SingleQuotedScalarString(i) for i in ids]
    )
    seq.fa.set_flow_style()
    logger.debug("Flow-style YAML sequence: %s", seq)
    return seq
