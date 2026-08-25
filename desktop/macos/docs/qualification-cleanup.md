# Qualification host cleanup (deprecated per-version artifacts)

After adopting the generic
`desktop/macos/scripts/qualify-desktop-beta-service.py` (also installed on the
Studio as `~/.hermes/scripts/qualify-desktop-beta-service.py`), remove the
hardcoded per-version helpers and state listed below. Deletion is **manual** —
do not automate removal from CI.

Confirm nothing still references a path (launchd plists, cron, Hermes jobs)
before deleting.

## Deprecated scripts (`~/.hermes/scripts/`)

| Artifact | Notes |
|---|---|
| `qualify-omi-macos-087-when-published.py` | One-shot `.87` qualifier; tag + paths hardcoded |
| `monitor-omi-macos-086-qualification.py` | `.86` monitor loop |
| `notify-omi-macos-088-qualified.py` | `.88` Telegram notify helper |
| `omi-macos-088-qualification-service.py` | `.88` long-running service; replaced by `qualify-desktop-beta-service.py` |

Related one-off dispatch helpers that mention a single tag (for example
`dispatch-omi-macos-087-after-swift-gate.py`) may be removed once their
candidate is finished; they are not part of the generic service.

## Deprecated state (`~/.hermes/state/`)

| Artifact | Notes |
|---|---|
| `omi-macos-088-qualification.json` | Persisted phase/attempt file for the `.88` service |

Also check `~/.hermes/cron/state/` for finished one-shot markers such as
`omi-macos-087-official-qualification.json` after the corresponding cron entry
is gone.

## Deprecated worktrees / caches (optional)

Per-tag disposable worktrees under `~/.cache/hermes/omi/.worktrees/qualify-*`
can be removed with `git -C ~/.cache/hermes/omi worktree remove …` once the
tag is qualified and no service still points at them. Prefer
`git worktree prune` after removal.

## Replacement

```bash
# Install / refresh the portable service on a qualification host
cp desktop/macos/scripts/qualify-desktop-beta-service.py \
  ~/.hermes/scripts/qualify-desktop-beta-service.py
chmod +x ~/.hermes/scripts/qualify-desktop-beta-service.py

# Babysit any candidate tag
~/.hermes/scripts/qualify-desktop-beta-service.py \
  --health-port 8765 \
  vX.Y.Z+BUILD-macos
```

See `qualification-environment.md` for runner provisioning, labels, and health
checks.
