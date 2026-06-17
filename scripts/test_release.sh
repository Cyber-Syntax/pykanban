#!/usr/bin/env bash
# Integration test for release.sh
# Run from the directory where release.sh and extract_changelog.sh live.
# Creates a sandbox, mocks all external commands, and checks the whole pipeline.
set -euo pipefail

TESTDIR=$(mktemp -d)
trap 'rm -rf "$TESTDIR"' EXIT

cp release.sh "$TESTDIR/"
cd "$TESTDIR"

# ---------- Mocks (PATH-based) ----------
MOCKDIR="$TESTDIR/mocks"
mkdir -p "$MOCKDIR"
export PATH="$MOCKDIR:$PATH"

# Mock git – write to current directory (which is $TESTDIR)
cat >"$MOCKDIR/git" <<'MOCKEOF'
#!/usr/bin/env bash
echo "$@" >> git_calls.log
if [[ "$1" == "rev-parse" ]]; then
    exit 1    # tag doesn't exist
fi
exit 0
MOCKEOF
chmod +x "$MOCKDIR/git"

# Mock gh – record arguments, and capture the notes file's content
# *before* release.sh deletes it. release.sh removes the --notes-file
# temp file immediately after gh returns, so this is the only window
# in which the content is still on disk for us to inspect.
cat >"$MOCKDIR/gh" <<'MOCKEOF'
#!/usr/bin/env bash
echo "$@" > gh_args.txt

args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
  if [[ "${args[i]}" == "--notes-file" ]]; then
    cp "${args[i+1]}" notes_content.txt
    echo "${args[i+1]}" > notes_file_path.txt
  fi
done

exit 0
MOCKEOF
chmod +x "$MOCKDIR/gh"

# Mock sha256sum – predictable hash
cat >"$MOCKDIR/sha256sum" <<'MOCKEOF'
#!/usr/bin/env bash
printf "abcdef1234567890  %s\n" "${@: -1}"
MOCKEOF
chmod +x "$MOCKDIR/sha256sum"

# Mock extract_changelog.sh (put in current dir, as release.sh calls ./extract_changelog.sh)
cat >extract_changelog.sh <<'MOCKSCRIPT'
#!/usr/bin/env bash
cat <<'ENDOUTPUT'
VERSION=0.1.0-alpha
NOTES<<EOF
### Added
- feature 1
- feature 2
EOF
ENDOUTPUT
MOCKSCRIPT
chmod +x extract_changelog.sh

# Create dummy AppImage
touch "PyKanban-x86_64.AppImage"

# ---------- Run ------------------------------------------------------------
echo "▶ Running release.sh..."
if bash release.sh; then
  echo "✔ release.sh exited successfully"
else
  echo "✖ release.sh exited with an error" >&2
  exit 1
fi

# ---------- Assertions -----------------------------------------------------
echo "  Running assertions..."

expected_appimage="PyKanban-0.1.0-alpha-x86_64.AppImage"
checksum_file="${expected_appimage}.sha256"

# 1. AppImage renamed
[[ -f "$expected_appimage" ]] || {
  echo "❌ AppImage missing"
  exit 1
}
echo "  ✅ AppImage renamed"

# 2. Checksum file
[[ -f "$checksum_file" ]] || {
  echo "❌ Checksum file missing"
  exit 1
}
checksum_content=$(cat "$checksum_file")
[[ "$checksum_content" == "abcdef1234567890  ${expected_appimage}" ]] || {
  echo "❌ Checksum mismatch: $checksum_content"
  exit 1
}
echo "  ✅ Checksum valid"

# 3. Git calls
[[ -f git_calls.log ]] || {
  echo "❌ git_calls.log missing"
  exit 1
}
grep -q "tag -a 0.1.0-alpha -m 0.1.0-alpha" git_calls.log || {
  echo "❌ git tag not called correctly"
  exit 1
}
grep -q "push origin 0.1.0-alpha" git_calls.log || {
  echo "❌ git push not called correctly"
  exit 1
}
echo "  ✅ Git commands correct"

# 4. GitHub release
[[ -f gh_args.txt ]] || {
  echo "❌ gh_args.txt missing"
  exit 1
}

# gh_args.txt must be exactly one line. If rename_and_checksum_appimage
# ever starts leaking its status messages onto stdout again, the
# captured "$appimage_path" variable becomes multi-line and corrupts the
# asset arguments passed to `gh` — this guards against that regression.
arg_lines=$(wc -l <gh_args.txt | tr -d ' ')
[[ "$arg_lines" -eq 1 ]] || {
  echo "❌ gh args spans multiple lines (asset path likely corrupted):"
  cat gh_args.txt
  exit 1
}

gh_args=$(cat gh_args.txt)
echo "  gh args: $gh_args"

# version present
echo "$gh_args" | grep -q "0.1.0-alpha" || {
  echo "❌ version missing from gh args"
  exit 1
}

# assets — checked as exact whitespace-delimited tokens rather than
# substrings, so a corrupted/extended path can't slip past the check
found_appimage=0
found_checksum=0
for tok in $gh_args; do
  [[ "$tok" == "$expected_appimage" ]] && found_appimage=1
  [[ "$tok" == "$checksum_file" ]] && found_checksum=1
done
[[ "$found_appimage" -eq 1 ]] || {
  echo "❌ AppImage asset missing or malformed"
  exit 1
}
[[ "$found_checksum" -eq 1 ]] || {
  echo "❌ checksum asset missing or malformed"
  exit 1
}
echo "  ✅ Assets attached"

# prerelease flag (-F / -- so the leading "--" isn't parsed as a grep option)
grep -qF -- "--prerelease" gh_args.txt || {
  echo "❌ prerelease flag missing"
  exit 1
}
echo "  ✅ Prerelease flag set"

# 5. Release notes content
# release.sh deletes the --notes-file temp file right after gh returns,
# so we rely on the copy our gh mock made while the file still existed.
[[ -f notes_content.txt ]] || {
  echo "❌ gh mock never saw a --notes-file argument"
  exit 1
}
notes_content=$(cat notes_content.txt)
echo "$notes_content" | grep -q "### Added" || {
  echo "❌ notes content missing '### Added'"
  exit 1
}
echo "$notes_content" | grep -q "feature 1" || {
  echo "❌ notes content missing 'feature 1'"
  exit 1
}
echo "  ✅ Release notes content correct"

# 6. Temp notes file should be cleaned up afterward
notes_file_path=$(cat notes_file_path.txt)
[[ ! -f "$notes_file_path" ]] || {
  echo "❌ temp notes file was not cleaned up: $notes_file_path"
  exit 1
}
echo "  ✅ Temp notes file cleaned up"

echo "🎉 All integration tests passed!"
