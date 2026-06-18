#!/bin/bash
set -e

APP_NAME="pykanban"
PROJECT_DIR="/home/developer/Documents/repositories/my-repos/pykanban/src/pykanban"
SPEC="packaging/pysidedeploy.spec"
BIN_PATH="build/pykanban.bin"
APPDIR="AppDir"

# ------------------------
# 1. build binary
# ------------------------
mkdir -p build

echo "🔧 Building PySide6 app..."
# uv run pyside6-deploy --config-file "$SPEC"
if uv run python -m nuitka \
  --onefile \
  --enable-plugin=pyside6 \
  --follow-imports \
  --file-reference-choice=runtime \
  --quiet \
  --noinclude-qt-translations \
  --include-data-dir="$PROJECT_DIR/data=data" \
  --output-dir=build \
  --output-filename=pykanban.bin \
  "$PROJECT_DIR/main.py"; then
  echo "✅ Nuitka build succeeded"
else
  echo "❌ Nuitka build failed"
  exit 1
fi

# ------------------------
# 2. sanity check
# ------------------------
if [ ! -f "$BIN_PATH" ]; then
  echo "❌ Build failed: $BIN_PATH not found"
  exit 1
fi
echo "✅ Binary found at $BIN_PATH"

# ------------------------
# 3. create AppDir
# ------------------------
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"

if cp "$BIN_PATH" "$APPDIR/usr/bin/$APP_NAME"; then
  echo "✅ Copied binary to AppDir"
else
  echo "❌ Failed to copy binary to AppDir"
  exit 1
fi

if chmod +x "$APPDIR/usr/bin/$APP_NAME"; then
  echo "✅ Set executable permission on binary"
else
  echo "❌ Failed to set executable permission"
  exit 1
fi

# ------------------------
# 4. copy static packaging files
# ------------------------
if cp packaging/AppRun "$APPDIR/AppRun"; then
  echo "✅ Copied AppRun"
else
  echo "❌ Failed to copy AppRun"
  exit 1
fi

if cp packaging/pykanban.desktop "$APPDIR/$APP_NAME.desktop"; then
  echo "✅ Copied .desktop file"
else
  echo "❌ Failed to copy .desktop file"
  exit 1
fi

if cp packaging/pykanban.png "$APPDIR/$APP_NAME.png"; then
  echo "✅ Copied icon"
else
  echo "❌ Failed to copy icon"
  exit 1
fi

if chmod +x "$APPDIR/AppRun"; then
  echo "✅ Set executable permission on AppRun"
else
  echo "❌ Failed to set executable permission on AppRun"
  exit 1
fi

# ------------------------
# 5. build AppImage
# ------------------------
echo "📦 Building AppImage..."
if ./appimagetool-x86_64.AppImage "$APPDIR" "build/PyKanban-x86_64.AppImage"; then
  echo "✅ AppImage saved to build/PyKanban-x86_64.AppImage"
else
  echo "❌ AppImage creation failed"
  exit 1
fi
