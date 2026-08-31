#!/usr/bin/env bash
# Generate a self-signed TLS cert for the Gateway HTTPS listener and load it into a Kubernetes Secret
# (ADR-0049 Q4: a Secret from a gen-certs script, NOT cert-manager — self-contained, reproducible,
# compose-parity with gen-dev-certs.sh). Run BEFORE `helm install` when the auth profile is enabled.
#
#   ./gen-certs.sh [namespace] [secret-name] [hostname]
#   HOST_IP=192.168.1.50 ./gen-certs.sh    # add a device-reachable IP to the SAN
#
# The SAN covers localhost + 127.0.0.1 (+ HOST_IP if set), so both in-host curl and a device validate.
# Idempotent: re-running replaces the Secret. Requires openssl + kubectl (KUBECONFIG set).
set -euo pipefail

NS="${1:-omi-dev}"
SECRET="${2:-omi-tls}"
HOST="${3:-localhost}"
HOST_IP="${HOST_IP:-}"
DIR="$(mktemp -d)"
trap 'rm -rf "$DIR"' EXIT

SAN="DNS:localhost,DNS:${HOST},IP:127.0.0.1"
[ -n "$HOST_IP" ] && SAN="${SAN},IP:${HOST_IP}"

echo "Generating self-signed cert (CN=${HOST}, SAN=${SAN})..."
openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
  -keyout "$DIR/tls.key" -out "$DIR/tls.crt" \
  -subj "/CN=${HOST}" -addext "subjectAltName=${SAN}"

echo "Creating Secret ${NS}/${SECRET} (tls)..."
kubectl -n "$NS" create secret tls "$SECRET" \
  --cert="$DIR/tls.crt" --key="$DIR/tls.key" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Done. Gateway HTTPS listener references Secret '${SECRET}' in namespace '${NS}'."
