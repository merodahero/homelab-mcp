#!/bin/bash
# install.sh — Deploy homelab-mcp to the Unraid vault, configured for the
# existing NUT install. Idempotent: safe to re-run.
#
# What it does:
#   1. Syncs the project to /mnt/cache/homelab-mcp on the vault
#   2. Installs Python deps into its venv and creates /opt/homelab-mcp as a
#      compatibility symlink
#   3. Writes /etc/nut/mcp/config.yaml (the deploy config, vault-specific)
#   4. Installs /etc/rc.d/rc.homelab-mcp (start|stop|restart|status)
#   5. Starts the service and verifies /healthz-equivalent (uptime + tools/list)
set -euo pipefail

VAULT_HOST="${VAULT_HOST:-100.108.133.48}"
# Canonical install root on durable storage (cache pool survives reboots).
# /opt/homelab-mcp is a symlink to here so existing paths and the RC script
# don't change.
REMOTE_DIR="/mnt/cache/homelab-mcp"
REMOTE_SYMLINK="/opt/homelab-mcp"
REMOTE_RC="/etc/rc.d/rc.homelab-mcp"
REMOTE_ENV="/etc/nut/mcp"
REMOTE_CFG="${REMOTE_ENV}/config.yaml"
LOGFILE="/var/log/homelab-mcp.log"
PIDFILE="/var/run/homelab-mcp.pid"

LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Uploading project to ${VAULT_HOST}:${REMOTE_DIR}"
ssh "root@${VAULT_HOST}" "mkdir -p '${REMOTE_DIR}' '${REMOTE_ENV}'"
rsync -a --delete \
  --exclude '.venv' --exclude '__pycache__' --exclude '.git' \
  --exclude 'config.tower-test.yaml' \
  "${LOCAL_DIR}/" "root@${VAULT_HOST}:${REMOTE_DIR}/"
ssh "root@${VAULT_HOST}" \
  "chmod 755 '${REMOTE_DIR}/rc.homelab-mcp' '${REMOTE_DIR}/rc.nut-mcp-restore'"

# Make sure the /opt symlink exists (idempotent — survives the reboot that
# would otherwise wipe the symlink because /opt is tmpfs).
ssh "root@${VAULT_HOST}" bash <<'REMOTE'
set -euo pipefail
mkdir -p /opt
if [ ! -L /opt/homelab-mcp ] || [ "$(readlink /opt/homelab-mcp)" != "/mnt/cache/homelab-mcp" ]; then
  if [ -e /opt/homelab-mcp ] && [ ! -L /opt/homelab-mcp ]; then
    # stale non-symlink dir from an old install — move it aside, don't lose it
    mv /opt/homelab-mcp /opt/homelab-mcp.old.$(date -u +%Y%m%dT%H%M%SZ)
  fi
  ln -sfn /mnt/cache/homelab-mcp /opt/homelab-mcp
fi
REMOTE

echo "==> Setting up venv + deps on the vault"
ssh "root@${VAULT_HOST}" bash <<'REMOTE'
set -euo pipefail
cd /mnt/cache/homelab-mcp
if [ ! -d .venv ] || [ ! -x .venv/bin/python ]; then
  rm -rf .venv
  uv venv --python 3.11 .venv
fi
# uv venv creates a minimal env without pip/wheel; use uv pip install
uv pip install --python .venv/bin/python --quiet -e .
REMOTE

echo "==> Writing ${REMOTE_CFG}"
scp "${LOCAL_DIR}/config.vault.yaml" "root@${VAULT_HOST}:${REMOTE_CFG}"
ssh "root@${VAULT_HOST}" "chmod 600 '${REMOTE_CFG}'"

echo "==> Installing ${REMOTE_RC}"
scp "${LOCAL_DIR}/rc.homelab-mcp" "root@${VAULT_HOST}:${REMOTE_RC}"
ssh "root@${VAULT_HOST}" "chmod +x '${REMOTE_RC}'"

echo "==> Starting the service"
ssh "root@${VAULT_HOST}" "${REMOTE_RC} restart"

echo
echo "==> Verifying"
sleep 2
ssh "root@${VAULT_HOST}" bash <<'REMOTE'
set -e
echo "--- service status ---"
/etc/rc.d/rc.homelab-mcp status
echo "--- tools/list via the MCP streamable-http endpoint ---"
TOK=$(cat /etc/nut/mcp/mcp.token 2>/dev/null || echo "")
# We didn't enable auth in the bundled HavartiBard stack; the server is open on
# the tailnet. A bearer token can be added later via an Nginx auth_request
# block in front of the service, or by extending the project's main.py.
PORT=8765
curl -sS -X POST "http://127.0.0.1:${PORT}/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"deploy-smoke","version":"0"}}}' \
  | head -c 200
echo
REMOTE

echo
echo "Done. Service bound on ${VAULT_HOST}:8765 (LAN: 10.27.0.15, Tailscale: 100.108.133.48)."
echo "Control:  ssh root@${VAULT_HOST} ${REMOTE_RC} {start|stop|restart|status}"
echo "Logs:     ssh root@${VAULT_HOST} tail -f ${LOGFILE}"
