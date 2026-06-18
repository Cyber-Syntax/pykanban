#!/usr/bin/env bash

# -----------------------------------------------------------------------------
# Clear settings Script
#
# Purpose:
#   Automate testing of a "first run" application state by:
#     1. Removing the application's project directory from Documents
#     2. Removing the application's configuration directory from ~/.config
#
# Usage:
#   ./clear_settings.sh
#
# Update the variables below to match your project.
# -----------------------------------------------------------------------------

set -o errexit
set -o nounset
set -o pipefail

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

PROJECT_NAME="pykanban-projects"

DOCUMENTS_PROJECT_DIR="${HOME}/Documents/${PROJECT_NAME}"
CONFIG_PROJECT_DIR="${HOME}/.config/pykanban"

# Full path to your application executable.
# APP_EXECUTABLE="uv run pykanban"

# -----------------------------------------------------------------------------
# Functions
# -----------------------------------------------------------------------------

cleanup() {
  :
}

handle_signal() {
  printf 'Script interrupted.\n' >&2
  return 130
}

validate_path() {
  local path

  path="$1"

  if [[ -z "${path// /}" ]]; then
    printf 'ERROR: Empty path received.\n' >&2
    return 1
  fi

  if [[ "${path}" == "/" ]]; then
    printf 'ERROR: Refusing to operate on root directory.\n' >&2
    return 1
  fi
}

remove_directory() {
  local target_dir

  target_dir="$1"

  if ! validate_path "${target_dir}"; then
    return 1
  fi

  if [[ ! -e "${target_dir}" ]]; then
    printf 'Directory not found, skipping: %s\n' "${target_dir}"
    return 0
  fi

  if ! trash-put -- "${target_dir}"; then
    printf 'ERROR: Failed to remove directory: %s\n' "${target_dir}" >&2
    return 1
  fi

  printf 'Removed: %s\n' "${target_dir}"
}

validate_application() {
  if [[ -z "${APP_EXECUTABLE// /}" ]]; then
    printf 'ERROR: APP_EXECUTABLE is empty.\n' >&2
    return 1
  fi

  if [[ ! -f "${APP_EXECUTABLE}" ]]; then
    printf 'ERROR: Application not found: %s\n' "${APP_EXECUTABLE}" >&2
    return 1
  fi

  if [[ ! -x "${APP_EXECUTABLE}" ]]; then
    printf 'ERROR: Application is not executable: %s\n' "${APP_EXECUTABLE}" >&2
    return 1
  fi
}

main() {
  trap cleanup EXIT
  trap 'handle_signal' INT TERM

  printf '========================================\n'
  printf ' Resetting application state\n'
  printf '========================================\n'

  if ! remove_directory "${DOCUMENTS_PROJECT_DIR}"; then
    printf 'ERROR: Failed while removing Documents directory.\n' >&2
    return 1
  fi

  if ! remove_directory "${CONFIG_PROJECT_DIR}"; then
    printf 'ERROR: Failed while removing config directory.\n' >&2
    return 1
  fi
}

main "$@"
