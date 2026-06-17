#!/bin/bash
set -e

APP_NAME="pykanban"

SPEC="packaging/pysidedeploy.spec"
BIN_PATH="build/pykanban.bin"
APPDIR="AppDir"

# ------------------------
# 1. build binary
# ------------------------
mkdir -p build

echo "🔧 Building PySide6 app..."
uv run pyside6-deploy --config-file "$SPEC"

# ------------------------
# 2. sanity check
# ------------------------
if [ ! -f "$BIN_PATH" ]; then
  echo "❌ Build failed: $BIN_PATH not found"
  exit 1
fi

# ------------------------
# 3. create AppDir
# ------------------------
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"

cp "$BIN_PATH" "$APPDIR/usr/bin/$APP_NAME"
chmod +x "$APPDIR/usr/bin/$APP_NAME"

# ------------------------
# 4. copy static packaging files
# ------------------------
cp packaging/AppRun "$APPDIR/AppRun"
cp packaging/pykanban.desktop "$APPDIR/$APP_NAME.desktop"
cp packaging/pykanban.png "$APPDIR/$APP_NAME.png"

chmod +x "$APPDIR/AppRun"

# ------------------------
# 5. build AppImage
# ------------------------
echo "📦 Building AppImage..."
./appimagetool-x86_64.AppImage "$APPDIR" "build/PyKanban-x86_64.AppImage"

echo "✅ AppImage saved to build/PyKanban-x86_64.AppImage"
