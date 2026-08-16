# Omi v5

This repository is the rewrite-only Omi monorepo. It contains the React Native product client, the native codec boundary, and the typed platform contracts required by the rewritten backend.

The standalone `main` branch is mirrored commit-for-commit to `BasedHardware/omi:v5`. Run `bun run setup` once, `bun run check` before committing, and `bun run push:v5` to publish the verified commit to the mirror branch.

The example backend lives at `/Users/undivisible/projects/omi-platform-integration` on `codex/track3-backend-integration` and serves the ratified `/v1/*` contract locally on `127.0.0.1:4851`.
