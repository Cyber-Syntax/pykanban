#!/usr/bin/env bash
set -euo pipefail

APP_NAME="PyKanban"
CHANGELOG_SCRIPT="./scripts/extract_changelog.sh"
BUILD_DIR="${BUILD_DIR:-./build}"
DEFAULT_APPIMAGE="${BUILD_DIR}/PyKanban-x86_64.AppImage"

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
  local tag="v${VERSION}"

  if git rev-parse "$tag" >/dev/null 2>&1; then
    printf "⚠️ Tag already exists: %s\n" "$tag" >&2
    return 1
  fi

  git tag -a "$tag" -m "$tag"
  git push origin HEAD --tags
  return 0
}

rename_and_checksum_appimage() {
  local version="$1"
  local appimage_file="${2:-$DEFAULT_APPIMAGE}"

  if [[ ! -f "$appimage_file" ]]; then
    printf "ERROR: AppImage not found: %s\n" "$appimage_file" >&2
    return 1
  fi

  local new_name="PyKanban-${version}-x86_64.AppImage"
  local dest="${BUILD_DIR}/${new_name}"

  cp "$appimage_file" "$dest"
  printf "📦 Copied AppImage to %s\n" "$dest" >&2

  sha256sum "$dest" >"${dest}.sha256"
  printf "🔒 Checksum saved to %s\n" "${dest}.sha256" >&2

  echo "$dest"
}

create_github_release() {
  local version="$1"
  local notes="$2"
  shift 2
  local assets=("$@")

  local release_tag="v${version}"
  printf "🚀 Creating GitHub release %s...\n" "$release_tag" >&2

  local notes_file
  notes_file=$(mktemp)
  printf "%s\n" "$notes" >"$notes_file"

  local prerelease_flag=""
  if [[ "$version" =~ (alpha|beta|rc|pre) ]]; then
    prerelease_flag="--prerelease"
  fi

  local rc=0
  gh release create "$release_tag" \
    --title "$APP_NAME-$release_tag" \
    --notes-file "$notes_file" \
    $prerelease_flag \
    "${assets[@]}" || rc=$?

  rm -f "$notes_file"
  return $rc
}

main() {
  printf "🚀 Starting release pipeline...\n" >&2

  extract_release_data || return 1

  printf "📦 Version: %s\n" "$VERSION" >&2
  printf "📝 Notes extracted\n" >&2

  local appimage_path
  appimage_path=$(rename_and_checksum_appimage "$VERSION") || return 1

  git_tag_release || return 1

  create_github_release "$VERSION" "$NOTES" "$appimage_path" "${appimage_path}.sha256"

  printf "✅ Release completed successfully!\n" >&2
  return 0
}

main "$@"
