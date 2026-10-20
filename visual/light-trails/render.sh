#!/bin/sh
# usage: render.sh <virtual-ms> <out.png> [page.html]
D=$(cd "$(dirname "$0")" && pwd)
P=${3:-$D/preview.html}
"$HOME/Library/Caches/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-mac-arm64/chrome-headless-shell" \
  --headless --hide-scrollbars --window-size=900,640 --virtual-time-budget="$1" \
  --screenshot="$2" "file://$P" >/dev/null 2>&1
