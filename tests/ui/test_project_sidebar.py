"""Tests for the project sidebar widget."""

from __future__ import annotations

from unittest.mock import MagicMock

from pykanban.app import KanbanApp
from pykanban.models import Project
from pykanban.ui.project_sidebar import ProjectSidebar


def _make_project(project_id: str, title: str, archived: bool) -> MagicMock:
    project = MagicMock(spec=Project)
    project.project_id = project_id
    project.title = title
    project.archived = archived
    return project


def _make_sidebar() -> ProjectSidebar:
    app = MagicMock(spec=KanbanApp)
    app.state = MagicMock()
    app.state.projects = MagicMock()
    app.state.projects.projects_by_id = {}
    return ProjectSidebar(app)


def test_refresh_routes_projects_into_tab_lists() -> None:
    """Active and archived projects should populate separate tabs."""
    sidebar = _make_sidebar()

    projects = [
        _make_project("p1", "Project One", archived=False),
        _make_project("p2", "Archived One", archived=True),
        _make_project("p3", "Project Two", archived=False),
    ]

    sidebar.refresh(projects)

    assert sidebar.tabs.count() == 2
    assert sidebar.tabs.tabText(0) == "Projects"
    assert sidebar.tabs.tabText(1) == "Archived"
    assert sidebar.active_list.count() == 2
    assert sidebar.archived_list.count() == 1
    assert sidebar.active_list.item(0).text() == "Project One"
    assert sidebar.archived_list.item(0).text() == "Archived One"


def test_project_click_emits_selection_signal() -> None:
    """Clicking a project item should emit the project id."""
    sidebar = _make_sidebar()
    project_selected = MagicMock()
    sidebar.project_selected.connect(project_selected)

    sidebar.refresh([_make_project("p1", "Project One", archived=False)])

    sidebar._on_item_clicked(sidebar.active_list.item(0))

    project_selected.assert_called_once_with("p1")


def test_sidebar_exposes_tabs_and_create_button() -> None:
    """The sidebar should expose tabs and the new-project action."""
    sidebar = _make_sidebar()
    sidebar.show()

    assert sidebar.isVisible() is True
    assert sidebar.tabs.count() == 2
    assert sidebar.new_button.text() == "New project"
