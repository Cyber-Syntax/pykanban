#!/usr/bin/env bash
set -euo pipefail

APP_NAME="PyKanban"
CHANGELOG_SCRIPT="./extract_changelog.sh"

DEFAULT_APPIMAGE="../PyKanban-x86_64.AppImage"

trap 'printf "❌ Interrupted release pipeline\n" >&2' INT TERM

extract_release_data() {
  local raw version notes

  if ! raw=$("$CHANGELOG_SCRIPT"); then
    printf "ERROR: failed to execute changelog script\n" >&2
    return 1
  fi

  version=$(printf "%s\n" "$raw" | grep '^VERSION=' | cut -d'=' -f2- | tr -d '[:space:]')
  notes=$(printf "%s\n" "$raw" | awk '/^NOTES<<EOF/{flag=1;next}/^EOF/{flag=0}flag')

  if [[ -z "${version// /}" ]]; then
    printf "ERROR: VERSION is empty\n" >&2
    return 1
  fi

  VERSION="$version"
  NOTES="$notes"
  return 0
}

git_tag_release() {
  local tag="$VERSION"

  if git rev-parse "$tag" >/dev/null 2>&1; then
    printf "⚠️ Tag already exists: %s\n" "$tag" >&2
    return 1
  fi

  git tag -a "$tag" -m "$tag"
  git push origin "$tag"

  return 0
}

# ----------------------------------------------------------------------
# rename the AppImage and create a .sha256 checksum file
# ----------------------------------------------------------------------
rename_and_checksum_appimage() {
  local version="$1"
  local appimage_file="${2:-$DEFAULT_APPIMAGE}"

  if [[ ! -f "$appimage_file" ]]; then
    printf "ERROR: AppImage not found: %s\n" "$appimage_file" >&2
    return 1
  fi

  local new_name="PyKanban-${version}-x86_64.AppImage"
  mv "$appimage_file" "$new_name"
  printf "📦 Renamed AppImage to %s\n" "$new_name"

  # Create checksum in the standard sha256sum format
  sha256sum "$new_name" >"${new_name}.sha256"
  printf "🔒 Checksum saved to %s\n" "${new_name}.sha256"

  # Return the new filename so later steps can use it
  echo "$new_name"
}

# ----------------------------------------------------------------------
# uses a temporary file for notes to avoid shell metacharacter issues
# and attaches the AppImage + checksum as release assets.
# ----------------------------------------------------------------------
create_github_release() {
  local version="$1"
  local notes="$2"
  shift 2
  local assets=("$@")

  printf "🚀 Creating GitHub release %s...\n" "$version"

  local notes_file
  notes_file=$(mktemp)
  printf "%s\n" "$notes" >"$notes_file"

  local prerelease_flag=""
  if [[ "$version" =~ (alpha|beta|rc|pre) ]]; then
    prerelease_flag="--prerelease"
  fi

  local rc=0
  gh release create "$version" \
    --title "$APP_NAME-$version" \
    --notes-file "$notes_file" \
    $prerelease_flag \
    "${assets[@]}" || rc=$?

  rm -f "$notes_file" # ← clean up immediately, even on failure
  return $rc
}

main() {
  printf "🚀 Starting release pipeline...\n"

  # 1. Get version and notes from CHANGELOG.md
  extract_release_data || return 1

  printf "📦 Version: %s\n" "$VERSION"
  printf "📝 Notes extracted\n"

  # 2. Rename the built AppImage and create the checksum file
  local appimage_path
  appimage_path=$(rename_and_checksum_appimage "$VERSION") || return 1

  # 3. Tag the release in git
  git_tag_release || return 1

  # 4. Create GitHub release with the AppImage, checksum, and notes
  create_github_release "$VERSION" "$NOTES" "$appimage_path" "${appimage_path}.sha256"

  printf "✅ Release completed successfully!\n"
  return 0
}

main "$@"
