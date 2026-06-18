# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1-alpha]

### Changed

- Changed appimage build script to use nuitka instead of pyside6-deploy which that was also using nuitka under the hood.

### Fixed

- Included learn-pykanban project to builded appimage.

## [0.1.0-alpha] - 2026-06-17

### Added

- Added project rename/create/delete/archive/unarchive functionality.
- Added task add/delete functionality.
- Added task card drag-and-drop functionality to move tasks between columns.
- Added task card rendering functionality to display task details on the card.
- Added task editor status/priority toggle functionality.
- Added task editor edit body functionality.
- Added task editor functionality to edit task details and save changes.
- Added sidebar for selecting projects and viewing archived projects.
- Added button to sidebar for creating new projects.
- Added sidebar with project/archived tabbed view.
- Added sidebar hide functionality to toggle the visibility of the sidebar.
- Added kanban board functionality to display columns and tasks.
- Added kanban board labeling functionality to show how many tasks are in each column.
- Added column functionality to hide/show more than 10 tasks on DONE column.
- Added task card styling to show task description/status/priority and subtasks progress bar.
- Added background watcher to be able to detect external changes (e.g neovim
  change the task file, delete etc.).
  - External changes while PyKanban is running are not supported and discouraged, use with caution.
    - This technically works for partial changes like editing task status/priority but I couldn't support it fully which there is a lot of edge cases to handle.
  - External changes while PyKanban is not running are partially supported but it is still experimental.
    - Make sure to use the same schema as the one used by PyKanban to avoid conflicts.
- Added logger for better debug.

[0.1.0-alpha]: https://github.com/Cyber-Syntax/my-unicorn/compare/v0.1.0-alpha...HEAD
