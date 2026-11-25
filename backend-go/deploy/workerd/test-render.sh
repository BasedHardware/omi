#!/usr/bin/env bash
set -euo pipefail

chart="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
digest="sha256:$(printf '%064d' 1)"
render() {
  helm template prod-omi-workerd "$chart" --namespace prod-omi-backend \
    -f "$chart/values-prod.yaml" --set-string "image.digest=$digest" \
    --set-string intake.hostname=workerd.example.com \
    --set-string intake.addressName=workerd-test-ip \
    --set-string intake.tlsSecretName=workerd-test-tls \
    --set-string intake.audience=https://workerd.example.com \
    --set-string intake.caller=producer@based-hardware.iam.gserviceaccount.com \
    --set-string intake.firestoreServiceAccount=workerd@based-hardware.iam.gserviceaccount.com "$@"
}

disabled="$(render --set intake.enabled=false,migration.enabled=false)"
enabled="$(render --set intake.enabled=true,migration.enabled=true)"
for fragment in 'kind: Gateway' 'kind: HTTPRoute' 'name: WORKER_EPISODE_INTAKE_AUDIENCE' \
    'name: WORKER_EPISODE_INTAKE_CALLER' 'kind: Job'; do
  if [[ "$disabled" == *"$fragment"* || "$enabled" != *"$fragment"* ]]; then
    echo "Unexpected boolean switch behavior for $fragment" >&2
    exit 1
  fi
done

for switch in intake.enabled migration.enabled; do
  if result="$(render --set-string "$switch=false" 2>&1)" ||
      [[ "$result" != *"$switch:"* || "$result" != *boolean* ]]; then
    echo "Expected a boolean validation error for $switch" >&2
    echo "$result" >&2
    exit 1
  fi
done

# SCA-3883 release identity: stable for the same inputs, sensitive to each of them, and
# refuses rather than guessing.
identity="$chart/release-identity.sh"
other="sha256:$(printf '%064d' 2)"
first="$("$identity" --digest "$digest")"
[[ "$first" == "$("$identity" --digest "$digest")" ]] || { echo 'release identity is not stable' >&2; exit 1; }
[[ "$first" == *"\"backend_go_tree\":\"$(git -C "$chart" rev-parse HEAD:backend-go)\""* ]] ||
  { echo 'release identity does not report the backend-go tree' >&2; exit 1; }
rendered_of() { sed -E 's/.*"rendered_sha256":"([a-f0-9]{64})".*/\1/' <<<"$1"; }
[[ "$(rendered_of "$first")" != "$(rendered_of "$("$identity" --digest "$other")")" ]] ||
  { echo 'release identity ignores the digest' >&2; exit 1; }
release_values="$(mktemp)"
trap 'rm -f "$release_values"' EXIT
printf 'intake:\n  enabled: true\n  hostname: workerd.example.com\n  addressName: workerd-test-ip\n  tlsSecretName: workerd-test-tls\n  audience: https://workerd.example.com\n  caller: producer@based-hardware.iam.gserviceaccount.com\n  firestoreServiceAccount: workerd@based-hardware.iam.gserviceaccount.com\n' > "$release_values"
[[ "$(rendered_of "$first")" != "$(rendered_of "$("$identity" --digest "$digest" -f "$release_values")")" ]] ||
  { echo 'release identity ignores Release values' >&2; exit 1; }
[[ "$first" == *'"helm_version":"v'* ]] || { echo 'release identity omits the helm version' >&2; exit 1; }
# The no -f form must also work under macOS /bin/bash 3.2 (empty arrays under set -u). Linux CI
# runs bash 5, so this case is exercised only on macOS developer machines.
[[ "$(/bin/bash "$identity" --digest "$digest")" == "$first" ]] ||
  { echo 'release identity differs under /bin/bash' >&2; exit 1; }
for bad in '--digest sha256:abc' "--digest $digest --ref no-such-ref" "--digest $digest -f /nonexistent.yaml" \
    "--digest $digest --verify-image invalid.invalid/workerd"; do
  # shellcheck disable=SC2086
  if "$identity" $bad >/dev/null 2>&1; then echo "release identity accepted: $bad" >&2; exit 1; fi
done

# A synthetic commit whose backend-go tree differs only in values-prod.yaml. The identity must
# report that tree and render it, while the working copy stays untouched.
repo_root="$(git -C "$chart" rev-parse --show-toplevel)"
head_commit="$(git -C "$repo_root" rev-parse HEAD)"
index="$(mktemp)"
trap 'rm -f "$release_values" "$index"' EXIT
GIT_INDEX_FILE="$index" git -C "$repo_root" read-tree "$head_commit"
changed_blob="$( (git -C "$repo_root" show "$head_commit:backend-go/deploy/workerd/values-prod.yaml"; printf '# identity fixture\nreplicaCount: 3\n') |
  git -C "$repo_root" hash-object -w --stdin)"
GIT_INDEX_FILE="$index" git -C "$repo_root" update-index --cacheinfo "100644,$changed_blob,backend-go/deploy/workerd/values-prod.yaml"
# A fixed identity: CI runners have no git user, and the fixture commit is never pushed.
fixture_commit="$(GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@invalid GIT_COMMITTER_NAME=fixture \
  GIT_COMMITTER_EMAIL=fixture@invalid git -C "$repo_root" commit-tree "$(GIT_INDEX_FILE="$index" git -C "$repo_root" write-tree)" -p "$head_commit" -m identity-fixture)"
fixture="$("$identity" --digest "$digest" --ref "$fixture_commit")"
[[ "$fixture" == *"\"backend_go_tree\":\"$(git -C "$repo_root" rev-parse "$fixture_commit:backend-go")\""* ]] ||
  { echo 'release identity does not follow --ref' >&2; exit 1; }
[[ "$(rendered_of "$fixture")" != "$(rendered_of "$first")" ]] ||
  { echo 'release identity renders the working copy instead of the --ref tree' >&2; exit 1; }
# At install time the checkout must equal --ref: HEAD's worktree is not the fixture commit.
"$identity" --digest "$digest" --check-worktree >/dev/null ||
  { echo 'release identity refused a clean checkout' >&2; exit 1; }
if "$identity" --digest "$digest" --ref "$fixture_commit" --check-worktree >/dev/null 2>&1; then
  echo 'release identity accepted a checkout that differs from --ref' >&2; exit 1
fi

# --verify-image with a stub docker: accept a matching tree label, refuse a mismatch, accept an
# unlabelled legacy image only when its revision is exactly the --ref commit.
stub="$(mktemp -d)"
trap 'rm -rf "$release_values" "$index" "$stub"' EXIT
cat > "$stub/docker" <<'STUB'
#!/usr/bin/env bash
case "$*" in
  *omi.workerd.backend-go-tree*) printf '%s\n' "$STUB_TREE" ;;
  *org.opencontainers.image.revision*) printf '%s\n' "$STUB_REVISION" ;;
  *) exit 1 ;;
esac
STUB
chmod +x "$stub/docker"
head_tree="$(git -C "$repo_root" rev-parse HEAD:backend-go)"
verify() { PATH="$stub:$PATH" STUB_TREE="$1" STUB_REVISION="$2" "$identity" --digest "$digest" --verify-image gcr.io/x/workerd >/dev/null 2>&1; }
verify "$head_tree" '' || { echo 'verify-image refused a matching tree label' >&2; exit 1; }
if verify "$(printf '%040d' 7)" ''; then echo 'verify-image accepted a mismatching tree' >&2; exit 1; fi
verify '<no value>' "$head_commit" || { echo 'verify-image refused a legacy image of the exact commit' >&2; exit 1; }
if verify '<no value>' "$fixture_commit"; then echo 'verify-image accepted a legacy image of another commit' >&2; exit 1; fi
if verify '' ''; then echo 'verify-image accepted an image with neither label' >&2; exit 1; fi

echo 'workerd chart render and release identity checks passed'
