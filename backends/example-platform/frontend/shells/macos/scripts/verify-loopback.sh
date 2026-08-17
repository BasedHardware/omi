#!/bin/bash
# Assert a running shell binds 127.0.0.1 only — never all-interfaces / LAN.
# History: NWListener(using:on:) silently binds *:port; a prior LoopbackServer
# published the app bundle to the LAN while 127.0.0.1 checks still passed.
#
# Usage: verify-loopback.sh [port]
#   port defaults to OMI_SURFACE_PORT, else 5290.
#
# Exit 0 only when every assertion passed. A skipped LAN check is never a pass.
set -euo pipefail

port="${1:-${OMI_SURFACE_PORT:-5290}}"
if [[ ! "$port" =~ ^[0-9]+$ ]] || (( port < 1 || port > 65535 )); then
  echo "ERROR: port must be an integer 1..65535 (got '$port')" >&2
  echo "VERDICT: loopback-bind FAIL (bad-port)"
  exit 1
fi

verdict_fail() {
  local reason="$1"
  shift
  echo "ERROR: $*" >&2
  echo "VERDICT: loopback-bind FAIL (${reason})"
  exit 1
}

# --- 1. Listening address must be exactly 127.0.0.1 ---
lsof_out=""
lsof_status=0
lsof_out="$(lsof -nP -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null)" || lsof_status=$?
if (( lsof_status != 0 )) || [[ -z "${lsof_out}" ]]; then
  verdict_fail "not-listening" \
    "nothing listening on TCP port ${port} (is the shell running?). Start it, then re-run this check."
fi

found_listen=0
while IFS= read -r line; do
  [[ -z "$line" || "$line" == COMMAND* ]] && continue
  # NAME column ends with: TCP <addr:port> (LISTEN)  — parse addr, never substring-grep.
  if [[ ! "$line" =~ TCP[[:space:]]+([^[:space:]]+)[[:space:]]+\(LISTEN\) ]]; then
    continue
  fi
  endpoint="${BASH_REMATCH[1]}"
  # Strip IPv6 brackets if present: [addr]:port → addr / port
  if [[ "$endpoint" =~ ^\[(.+)\]:([0-9]+)$ ]]; then
    addr="${BASH_REMATCH[1]}"
    ep_port="${BASH_REMATCH[2]}"
  elif [[ "$endpoint" =~ ^(.+):([0-9]+)$ ]]; then
    addr="${BASH_REMATCH[1]}"
    ep_port="${BASH_REMATCH[2]}"
  else
    verdict_fail "unparseable-lsof" "could not parse lsof endpoint from: ${line}"
  fi
  if [[ "$ep_port" != "$port" ]]; then
    continue
  fi
  found_listen=1
  if [[ "$addr" != "127.0.0.1" ]]; then
    verdict_fail "not-loopback" \
      "TCP :${port} is listening on '${addr}', not exactly 127.0.0.1 (all-interfaces/LAN bind leaks the surface bundle)"
  fi
done <<< "$lsof_out"

if (( found_listen == 0 )); then
  verdict_fail "not-listening" \
    "lsof returned no TCP LISTEN row for port ${port}. Output was:"$'\n'"${lsof_out}"
fi

echo "ok: lsof shows TCP 127.0.0.1:${port} (LISTEN)"

# --- 2. Primary LAN IPv4 (skip loudly if absent — never report as pass) ---
lan_ip=""
for iface in en0 en1; do
  candidate="$(ipconfig getifaddr "$iface" 2>/dev/null || true)"
  if [[ -n "$candidate" ]]; then
    lan_ip="$candidate"
    break
  fi
done

if [[ -z "$lan_ip" ]]; then
  echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" >&2
  echo "SKIPPED (LOUD): no primary LAN IPv4 on en0/en1 — cannot prove" >&2
  echo "the surface is unreachable from the network. This is NOT a pass." >&2
  echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" >&2
  echo "VERDICT: loopback-bind INCOMPLETE (no-lan)"
  exit 1
fi

echo "ok: primary LAN IPv4 is ${lan_ip}"

# --- 3. HTTP to LAN IP must fail to connect ---
# curl success = bundle is LAN-published → hard fail.
# Connection refused / timeout / unreachable = expected for loopback-only bind.
curl_status=0
curl -sS --connect-timeout 2 --max-time 3 \
  "http://${lan_ip}:${port}/" -o /dev/null 2>/dev/null || curl_status=$?

if (( curl_status == 0 )); then
  verdict_fail "lan-reachable" \
    "http://${lan_ip}:${port}/ connected successfully — surface is published on the LAN, not loopback-only"
fi

echo "ok: http://${lan_ip}:${port}/ failed to connect (curl exit ${curl_status})"

# --- 4. Machine-greppable verdict ---
echo "VERDICT: loopback-bind PASS"
exit 0
