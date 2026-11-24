#!/usr/bin/env bash
# Print the workerd release identity a Release go-ahead binds to (SCA-3883).
#
#   release-identity.sh --digest sha256:<64 hex> --ref <source SHA> [-f release-values.yaml ...]
#                       [--verify-image gcr.io/based-hardware/workerd] [--check-worktree]
#
# Output: one JSON object with:
#   backend_go_tree  git tree of backend-go/ at --ref (the image build context, this chart and
#                    values-prod.yaml)
#   digest           the image digest
#   helm_version     the helm client that rendered (render output can differ across versions)
#   rendered_sha256  sha256 of the production manifest rendered from that tree with the digest
#                    and the same -f files passed to the matching `helm upgrade --install`
# A go-ahead names the whole object. It stays valid while main moves, as long as rerunning this
# script at install time prints the same object. --verify-image also checks that the digest's
# omi.workerd.backend-go-tree label equals backend_go_tree (needs registry read access). An image
# published before tree labels passes only if its revision label is exactly the --ref commit.
# --check-worktree refuses unless the checkout's backend-go/ (tracked and untracked files) equals
# the --ref tree; use it at install time, because helm installs from the working copy.
# Any failure (unknown ref, unreadable values, render error, label mismatch or unreadable
# label) exits nonzero: refuse, never assume a match.
set -euo pipefail

digest=''
ref='HEAD'
verify_repo=''
check_worktree=false
values=()
while (($#)); do
  case "$1" in
    --digest) digest="${2:-}"; shift 2 ;;
    --ref) ref="${2:-}"; shift 2 ;;
    -f) values+=(-f "${2:-}"); shift 2 ;;
    --verify-image) verify_repo="${2:-}"; shift 2 ;;
    --check-worktree) check_worktree=true; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ "$digest" =~ ^sha256:[a-f0-9]{64}$ ]] || { echo 'expected --digest sha256:<64 hex>' >&2; exit 2; }

repo="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
tree="$(git -C "$repo" rev-parse --verify --quiet "$ref^{commit}:backend-go")" || {
  echo "cannot resolve backend-go at $ref" >&2; exit 1; }
[[ "$tree" =~ ^[a-f0-9]{40}$ ]]
commit="$(git -C "$repo" rev-parse --verify "$ref^{commit}")"

if [[ "$check_worktree" == true ]]; then
  if ! git -C "$repo" diff --quiet "$commit" -- backend-go ||
      [[ -n "$(git -C "$repo" status --porcelain --untracked-files=all -- backend-go)" ]]; then
    echo "working copy backend-go/ differs from $ref; install from a clean checkout of $ref" >&2
    exit 1
  fi
fi

image_label() {
  docker buildx imagetools inspect "$verify_repo@$digest" --format "{{ index .Image.Config.Labels \"$1\" }}"
}
if [[ -n "$verify_repo" ]]; then
  label="$(image_label omi.workerd.backend-go-tree)" || {
    echo "cannot read the backend-go tree label of $verify_repo@$digest" >&2; exit 1; }
  if [[ -z "$label" || "$label" == '<no value>' ]]; then
    revision="$(image_label org.opencontainers.image.revision)" || {
      echo "cannot read the revision label of $verify_repo@$digest" >&2; exit 1; }
    [[ "$revision" == "$commit" ]] || {
      echo "unlabelled digest was built from '$revision', not $commit" >&2; exit 1; }
  elif [[ "$label" != "$tree" ]]; then
    echo "digest was built from backend-go tree '$label', not $tree" >&2; exit 1
  fi
fi

helm_version="$(helm version --template '{{ .Version }}')"
[[ -n "$helm_version" ]]

# Render from the exact tree, not the working copy, so local edits cannot change the identity.
scratch="$(mktemp -d)"
trap 'rm -r "$scratch"' EXIT
git -C "$repo" archive --format=tar "$tree" deploy/workerd | tar -x -C "$scratch"
chart="$scratch/deploy/workerd"
# ${values[@]+...} keeps an empty list valid under set -u on bash < 4.4.
rendered="$(helm template prod-omi-workerd "$chart" --namespace prod-omi-backend \
  -f "$chart/values-prod.yaml" ${values[@]+"${values[@]}"} --set-string "image.digest=$digest")"
rendered_sha256="$(printf '%s' "$rendered" | shasum -a 256 | cut -d' ' -f1)"

printf '{"backend_go_tree":"%s","digest":"%s","helm_version":"%s","rendered_sha256":"%s"}\n' \
  "$tree" "$digest" "$helm_version" "$rendered_sha256"
