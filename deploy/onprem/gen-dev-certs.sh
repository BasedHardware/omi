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

# CA
openssl req -x509 -newkey rsa:2048 -sha256 -days 825 -nodes \
  -keyout "$OUT/ca.key" -out "$OUT/ca.crt" -subj "/CN=Omi OnPrem Dev CA" 2>/dev/null

# Server key + cert (shared by kc-proxy and api-proxy), SAN = HOST_IP + localhost
openssl req -newkey rsa:2048 -nodes -keyout "$OUT/server.key" -out "$OUT/server.csr" \
  -subj "/CN=$HOST_IP" 2>/dev/null
cat > "$OUT/san.ext" <<EOF
subjectAltName=IP:$HOST_IP,DNS:localhost,IP:127.0.0.1
extendedKeyUsage=serverAuth
EOF
openssl x509 -req -in "$OUT/server.csr" -CA "$OUT/ca.crt" -CAkey "$OUT/ca.key" -CAcreateserial \
  -out "$OUT/server.crt" -days 825 -sha256 -extfile "$OUT/san.ext" 2>/dev/null

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

echo "Done:"
openssl x509 -in "$OUT/server.crt" -noout -subject -ext subjectAltName 2>/dev/null | sed 's/^/  /'
echo "  Install $OUT/ca.crt on the device as a user CA (Settings > Security > Install a certificate)."
