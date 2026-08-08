#!/usr/bin/env bash
# Reproducible self-signed TLS material for the on-prem dev stack (Keycloak + backend API proxies).
# Private keys are gitignored; re-run this to regenerate deterministically.
#
#   HOST_IP=192.168.100.122 ./gen-dev-certs.sh
#
# HOST_IP must be the address the mobile DEVICE uses to reach the host (the emulator/phone cannot use
# 127.0.0.1). The cert SAN covers that IP + localhost, so both the device and in-host calls validate.
# The CA (certs/ca.crt) must be trusted by the device (install as a user CA) and, if a proxy fetches
# over https, by the backend (mount + SSL_CERT_FILE). The compose's default backchannel JWKS is plain
# http on the internal network, so the backend needs no CA there.
set -euo pipefail
cd "$(dirname "$0")"

HOST_IP="${HOST_IP:-127.0.0.1}"
OUT=certs
mkdir -p "$OUT"

echo "Generating dev CA + server cert for HOST_IP=$HOST_IP -> $OUT/"

# CA — reuse an existing one so a rerun does NOT break devices that already trust ca.crt: replacing
# the CA is a rotation (every device must re-install the new ca.crt and the running proxies must
# restart with the new server cert). To rotate deliberately, delete certs/ca.crt + certs/ca.key first.
# stderr is intentionally NOT suppressed (under `set -e` a silent openssl failure would leave partial
# trust material with no diagnostics). basicConstraints/keyUsage mark ca.crt as a real CA so device
# installation and chain validation work on hosts whose openssl.cnf lacks x509_extensions=v3_ca.
if [ -f "$OUT/ca.crt" ] && [ -f "$OUT/ca.key" ]; then
  echo "Reusing existing CA ($OUT/ca.crt) — delete certs/ca.{crt,key} to rotate (requires device re-trust)."
else
  echo "Generating a new dev CA ($OUT/ca.crt) — install it on every device."
  openssl req -x509 -newkey rsa:2048 -sha256 -days 825 -nodes \
    -keyout "$OUT/ca.key" -out "$OUT/ca.crt" -subj "/CN=Omi OnPrem Dev CA" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign"
fi

# Server key + cert (shared by kc-proxy and api-proxy), SAN = HOST_IP + localhost. Regenerated every
# run (cheap, and it re-signs against the current CA); errors surface (no 2>/dev/null).
openssl req -newkey rsa:2048 -nodes -keyout "$OUT/server.key" -out "$OUT/server.csr" \
  -subj "/CN=$HOST_IP"
cat > "$OUT/san.ext" <<EOF
subjectAltName=IP:$HOST_IP,DNS:localhost,IP:127.0.0.1
extendedKeyUsage=serverAuth
EOF
openssl x509 -req -in "$OUT/server.csr" -CA "$OUT/ca.crt" -CAkey "$OUT/ca.key" -CAcreateserial \
  -out "$OUT/server.crt" -days 825 -sha256 -extfile "$OUT/san.ext"

# Combined bundle (system roots + our CA) for a backend that fetches JWKS over https (optional path).
# Locate the actual system CA bundle across distro layouts (Debian/Ubuntu, RHEL/Fedora, Alpine) — a
# missing file must not silently drop the system roots.
SYS_CA=""
for f in /etc/ssl/certs/ca-certificates.crt /etc/pki/tls/certs/ca-bundle.crt /etc/ssl/cert.pem; do
  [ -f "$f" ] && { SYS_CA="$f"; break; }
done
if [ -n "$SYS_CA" ]; then
  cat "$SYS_CA" "$OUT/ca.crt" > "$OUT/combined.pem"
else
  echo "  WARNING: no system CA bundle found; combined.pem holds only the dev CA (https JWKS to public issuers may fail)." >&2
  cp "$OUT/ca.crt" "$OUT/combined.pem"
fi

# Fail loudly if any expected artifact is missing or empty. `set -e` already aborts on an openssl
# error, but a silent partial state must never be mistaken for success (this script's whole job is
# producing trust material).
for artifact in ca.crt ca.key server.crt server.key combined.pem; do
  [ -s "$OUT/$artifact" ] || { echo "ERROR: expected $OUT/$artifact was not produced" >&2; exit 1; }
done

echo "Done:"
openssl x509 -in "$OUT/server.crt" -noout -subject -ext subjectAltName | sed 's/^/  /'
echo "  Install $OUT/ca.crt on the device as a user CA (Settings > Security > Install a certificate)."
