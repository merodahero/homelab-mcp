#!/usr/bin/env bash
# Regression test: neither boot restore nor installer may assume /opt exists.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RESTORE_SCRIPT="${REPO_DIR}/rc.nut-mcp-restore"
INSTALL_SCRIPT="${REPO_DIR}/install.sh"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "${TMPDIR}"' EXIT

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

# Guard the test sandbox before executing the production script. These
# overrides keep all test writes out of the host's /opt, /etc, and /var.
grep -q '^MCP_CACHE_DIR="${MCP_CACHE_DIR:-/mnt/cache/homelab-mcp}"$' "${RESTORE_SCRIPT}" || \
    fail "rc.nut-mcp-restore lacks a sandboxable MCP_CACHE_DIR"
grep -q '^OPT_DIR="${OPT_DIR:-/opt}"$' "${RESTORE_SCRIPT}" || \
    fail "rc.nut-mcp-restore lacks a sandboxable OPT_DIR"
grep -q '^RC_DIR="${RC_DIR:-/etc/rc.d}"$' "${RESTORE_SCRIPT}" || \
    fail "rc.nut-mcp-restore lacks a sandboxable RC_DIR"
grep -q '^LOG="${LOG:-/var/log/nut-mcp-restore.log}"$' "${RESTORE_SCRIPT}" || \
    fail "rc.nut-mcp-restore lacks a sandboxable LOG"

CACHE_DIR="${TMPDIR}/cache/homelab-mcp"
OPT_DIR="${TMPDIR}/opt"
RC_DIR="${TMPDIR}/etc/rc.d"
UPS_CONF="${TMPDIR}/etc/nut/ups.conf"
LOG="${TMPDIR}/var/log/nut-mcp-restore.log"

# Deliberately do not create ${OPT_DIR}; this models Unraid's tmpfs /opt at
# array start. The restore script must create it before moving or linking.
mkdir -p "${CACHE_DIR}/.venv" "${RC_DIR}" "$(dirname "${UPS_CONF}")" "$(dirname "${LOG}")"
MCP_CACHE_DIR="${CACHE_DIR}" OPT_DIR="${OPT_DIR}" RC_DIR="${RC_DIR}" \
UPS_CONF="${UPS_CONF}" LOG="${LOG}" HELPER="${TMPDIR}/missing-helper.py" \
    "${RESTORE_SCRIPT}"

[ -d "${OPT_DIR}" ] || fail "restore did not create the missing /opt parent"
[ -L "${OPT_DIR}/homelab-mcp" ] || fail "restore did not create the compatibility symlink"
[ "$(readlink "${OPT_DIR}/homelab-mcp")" = "${CACHE_DIR}" ] || \
    fail "restore symlink points somewhere other than the cache install"

# A stale directory must still be preserved rather than discarded. Re-running
# also proves the resulting symlink path remains idempotent.
rm "${OPT_DIR}/homelab-mcp"
mkdir "${OPT_DIR}/homelab-mcp"
touch "${OPT_DIR}/homelab-mcp/legacy-file"
MCP_CACHE_DIR="${CACHE_DIR}" OPT_DIR="${OPT_DIR}" RC_DIR="${RC_DIR}" \
UPS_CONF="${UPS_CONF}" LOG="${LOG}" HELPER="${TMPDIR}/missing-helper.py" \
    "${RESTORE_SCRIPT}"
[ -L "${OPT_DIR}/homelab-mcp" ] || fail "restore did not replace the stale directory"
shopt -s nullglob
stale_paths=("${OPT_DIR}"/homelab-mcp.old.*)
[ "${#stale_paths[@]}" -eq 1 ] || fail "restore did not preserve exactly one stale directory"
[ -f "${stale_paths[0]}/legacy-file" ] || fail "restore discarded stale directory contents"
MCP_CACHE_DIR="${CACHE_DIR}" OPT_DIR="${OPT_DIR}" RC_DIR="${RC_DIR}" \
UPS_CONF="${UPS_CONF}" LOG="${LOG}" HELPER="${TMPDIR}/missing-helper.py" \
    "${RESTORE_SCRIPT}"
[ -L "${OPT_DIR}/homelab-mcp" ] || fail "restore is not idempotent"

# The installer runs this in its remote shell; require the parent creation to
# occur before its first /opt/homelab-mcp test so the same boot condition holds.
mkdir_line=$(grep -n 'mkdir -p /opt' "${INSTALL_SCRIPT}" | head -n 1 | cut -d: -f1)
first_opt_test_line=$(grep -n '\[ ! -L /opt/homelab-mcp \]' "${INSTALL_SCRIPT}" | head -n 1 | cut -d: -f1)
[ -n "${mkdir_line}" ] && [ -n "${first_opt_test_line}" ] && [ "${mkdir_line}" -lt "${first_opt_test_line}" ] || \
    fail "install.sh does not create /opt before managing /opt/homelab-mcp"

printf 'PASS: missing /opt parent is recreated safely by boot restore and installer ordering is guarded\n'
