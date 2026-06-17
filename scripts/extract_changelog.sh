#!/usr/bin/env bash
set -euo pipefail

CHANGELOG_FILE="${1:-./CHANGELOG.md}"

main() {
  local first_header version notes

  if [[ ! -f "$CHANGELOG_FILE" ]]; then
    echo "ERROR: CHANGELOG.md not found at $CHANGELOG_FILE" >&2
    exit 1
  fi

  first_header=$(grep -m 1 '^## \[' "$CHANGELOG_FILE" || grep -m 1 '^## v' "$CHANGELOG_FILE" || true)

  if [[ -z "$first_header" ]]; then
    echo "ERROR: No version header found" >&2
    exit 1
  fi

  if [[ "$first_header" =~ ^\#\#\ \[([0-9]+\.[0-9]+\.[0-9]+[^]]*)\] ]]; then
    version="${BASH_REMATCH[1]}"
  elif [[ "$first_header" =~ ^\#\#\ (v[0-9]+\.[0-9]+\.[0-9]+.*) ]]; then
    version="${BASH_REMATCH[1]}"
  elif [[ "$first_header" =~ ^\#\#\ \[([Uu]nreleased)\] ]]; then
    version="${BASH_REMATCH[1]}"
  else
    echo "ERROR: Invalid version format: $first_header" >&2
    exit 1
  fi

  # Extract notes – stop at next version header OR at reference link lines
  notes=$(awk -v ver="$version" '
        BEGIN { found=0; capture=0; notes=""; }
        /^## \[/ || /^## v/ {
            if ($0 ~ ver && !found) {
                found=1; capture=1; next;
            } else if (capture==1) {
                capture=0;
            }
        }
        /^\[[^\]]*\]:/ {
            # stop capturing if we hit a reference link line
            if (capture==1) { capture=0; }
        }
        capture==1 { notes = notes $0 "\n"; }
        END { print notes; }
    ' "$CHANGELOG_FILE")

  echo "VERSION=$version"
  echo "NOTES<<EOF"
  echo "$notes"
  echo "EOF"
}

main "$@"
