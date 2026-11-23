#!/usr/bin/env bash
# Print the workerd release identity a Release go-ahead binds to (SCA-3883).
#
#   release-identity.sh --digest sha256:<64 hex> [--ref <git ref>] [-f release-values.yaml ...]
#
# Output: one JSON object with backend_go_tree (the git tree of backend-go/ at --ref, which
# covers the image build context, this chart and values-prod.yaml), the image digest, and
# rendered_sha256 (the sha256 of the production manifest rendered from that tree with the
# digest and any Release values files). A go-ahead names all three. It stays valid while
# main moves, as long as rerunning this script at install time prints the same object.
# Any failure (unknown ref, unreadable values, render error) exits nonzero: refuse, never
# assume a match.
set -euo pipefail

digest=''
ref='HEAD'
values=()
while (($#)); do
  case "$1" in
    --digest) digest="${2:-}"; shift 2 ;;
    --ref) ref="${2:-}"; shift 2 ;;
    -f) values+=(-f "${2:-}"); shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ "$digest" =~ ^sha256:[a-f0-9]{64}$ ]] || { echo 'expected --digest sha256:<64 hex>' >&2; exit 2; }

repo="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
tree="$(git -C "$repo" rev-parse --verify --quiet "$ref^{commit}:backend-go")" || {
  echo "cannot resolve backend-go at $ref" >&2; exit 1; }
[[ "$tree" =~ ^[a-f0-9]{40}$ ]]

# Render from the exact tree, not the working copy, so local edits cannot change the identity.
scratch="$(mktemp -d)"
trap 'rm -r "$scratch"' EXIT
git -C "$repo" archive --format=tar "$tree" deploy/workerd | tar -x -C "$scratch"
chart="$scratch/deploy/workerd"
rendered="$(helm template prod-omi-workerd "$chart" --namespace prod-omi-backend \
  -f "$chart/values-prod.yaml" "${values[@]}" --set-string "image.digest=$digest")"
rendered_sha256="$(printf '%s' "$rendered" | shasum -a 256 | cut -d' ' -f1)"

printf '{"backend_go_tree":"%s","digest":"%s","rendered_sha256":"%s"}\n' "$tree" "$digest" "$rendered_sha256"
