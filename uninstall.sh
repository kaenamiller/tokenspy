#!/usr/bin/env bash
set -euo pipefail

PURGE=false
for arg in "$@"; do
  [[ "$arg" == "--purge" ]] && PURGE=true
done

echo "==> Stopping and disabling tokenspyd…"
systemctl --user stop tokenspyd.service 2>/dev/null || true
systemctl --user disable tokenspyd.service 2>/dev/null || true
rm -f ~/.config/systemd/user/tokenspyd.service
systemctl --user daemon-reload

echo "==> Removing TokenSpy plasmoid…"
kpackagetool6 --type Plasma/Applet --remove com.kaena.tokenspy 2>/dev/null || true

echo "==> Uninstalling tokenspyd daemon…"
pipx uninstall tokenspyd 2>/dev/null || true

if $PURGE; then
  echo "==> Purging config and state files…"
  rm -rf ~/.config/tokenspy ~/.local/state/tokenspy
  echo "    Removed ~/.config/tokenspy and ~/.local/state/tokenspy"
else
  echo ""
  echo "Config and state files preserved:"
  echo "  ~/.config/tokenspy/"
  echo "  ~/.local/state/tokenspy/"
  echo "  Run with --purge to remove these too."
fi

echo ""
echo "✓ TokenSpy uninstalled."
