# Actions supply-chain hygiene guard

Manifest check `github-actions-hygiene`
(`.github/scripts/check_actions_hygiene.py`, fixtures in
`test_check_actions_hygiene.py`) rejects, for every root workflow and every
custom action under `.github/actions/` (nested action dirs included):

- Mutable third-party action refs. Every non-local `uses:` that is not a full
  40-hex commit SHA fails the check — version tags (`@v6`) and branch names
  (`@main`, `@master`, `@stable`) alike, because the action owner can retarget
  them. Pin third-party actions to a full commit SHA; `actions/*` first-party
  refs and `./`-local refs are exempt, and `docker://` actions only fail on
  `:latest`.
- Nested component-local workflow directories outside repo-root
  `.github/workflows/` (GitHub never executes them; legacy dirs live in a
  shrink-only ratchet, tracked by #11408).
- `flutter-buildrunner` cache keys embedding `github.run_id` (exact key never
  hits; parallel jobs race), including keys split across folded YAML scalars.
- `GITHUB_SHA`/`github.sha` provenance in any job that checks out an
  operator-selected ref — any `inputs.*` / `github.event.inputs.*` expression
  in the checkout `ref`, wherever it appears in the scalar (prefixed
  `refs/tags/${{ inputs.tag }}`, inside `${{ format(...) }}`, quoted, or
  folded). Provenance is per job: derive image/artifact identity from the
  checked-out tree (`git rev-parse --short=7 HEAD`), which on
  `workflow_dispatch` is not the run ref.

The check is selected by `.github/checks-manifest.yaml` for root workflow
paths, `.github/actions/**` metadata, and any nested `**/.github/workflows/**`
path, so a new component-local workflow cannot bypass the routing.
