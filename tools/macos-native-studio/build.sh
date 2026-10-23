#!/bin/sh
set -eu
TASK_SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TASK_REPO=$(CDPATH= cd -- "$TASK_SOURCE/../.." && pwd)
TASK_APP="$TASK_REPO/local-apps/Macro Studio.app"
mkdir -p "$TASK_APP/Contents/MacOS" "$TASK_APP/Contents/Resources" "$TASK_APP/Contents/Tools"
cp "$TASK_SOURCE/Info.plist" "$TASK_APP/Contents/Info.plist"
mkdir -p "$TASK_REPO/local-apps/.module-cache"
# Optional local VFS overlay for mixed CLT installations; never changes system files.
if [ "${MACRO_STUDIO_CLT_OVERLAY:-0}" = 1 ]; then
    printf '%s\n' '// Duplicate legacy SwiftBridging map hidden for this build only.' > "$TASK_REPO/local-apps/empty-legacy.modulemap"
    /usr/bin/python3 - "$TASK_REPO/local-apps" <<'PYOVERLAY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]);(p/'swift-clt-overlay.json').write_text(json.dumps({'version':0,'roots':[{'type':'file','name':'/Library/Developer/CommandLineTools/usr/include/swift/module.modulemap','external-contents':str(p/'empty-legacy.modulemap')}]}))
PYOVERLAY
    set -- -vfsoverlay "$TASK_REPO/local-apps/swift-clt-overlay.json"
else
    set --
fi
xcrun swiftc "$@" -target "$(uname -m)-apple-macos14.4" -module-cache-path "$TASK_REPO/local-apps/.module-cache-overlay" -swift-version 5 -O -framework AppKit -framework ScreenCaptureKit -framework Vision -framework ImageIO "$TASK_SOURCE/Sources/main.swift" -o "$TASK_APP/Contents/MacOS/MacroStudio"
xcrun clang -fmodules-cache-path="$TASK_REPO/local-apps/.module-cache" -O2 -fobjc-arc -framework Foundation -framework Vision -framework ImageIO "$TASK_REPO/tools/macos-window/vision-ocr.m" -o "$TASK_APP/Contents/Tools/vision-ocr"
codesign --force --sign "${MACRO_STUDIO_SIGN_IDENTITY:--}" --identifier io.crossmacro.macro-studio "$TASK_APP"
"$TASK_APP/Contents/MacOS/MacroStudio" --self-check
printf '%s\n' "$TASK_APP"
