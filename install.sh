#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(dirname "$(readlink -f "$0")")"

echo "==> Installing tokenspyd daemon via pipx…"
pipx install --force "$REPO_DIR"

echo "==> Installing systemd user unit…"
mkdir -p ~/.config/systemd/user
cp "$REPO_DIR/systemd/tokenspyd.service" ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now tokenspyd.service

echo "==> Installing TokenSpy plasmoid…"
kpackagetool6 --type Plasma/Applet --install "$REPO_DIR/plasmoid/package" \
  || kpackagetool6 --type Plasma/Applet --upgrade "$REPO_DIR/plasmoid/package"

echo "==> Running tokenspyd doctor…"
tokenspyd doctor || true

cat <<'EOF'

✓ TokenSpy is installed.

Right-click your desktop or panel → Add Widgets… → search "TokenSpy" to add it.

Config:  ~/.config/tokenspy/config.toml
State:   ~/.local/state/tokenspy/current.json
Logs:    journalctl --user -u tokenspyd -f

If Claude or Cursor show auth errors, see the config file for instructions.
EOF
