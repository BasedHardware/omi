# Omi v5

This repository is the rewrite-only Omi monorepo. It contains the React Native product client, the native codec boundary, and the typed platform contracts required by the rewritten backend.

The standalone `main` branch is mirrored commit-for-commit to `BasedHardware/omi:v5`. Run `bun run setup` once, `bun run check` before committing, and `bun run push:v5` to publish the verified commit to the mirror branch.

Run `bun run platforms:test` for clean iOS Simulator and macOS Debug compiles after Pods are installed. The bounded pre-push gate remains focused on contracts, TypeScript, React Native tests, and the native C++ boundary.

The example backend lives at `/Users/undivisible/projects/omi-platform-integration` on `codex/track3-backend-integration` and serves the ratified `/v1/*` contract locally on `127.0.0.1:4851`.

`apps/backend-worker` is the Cloudflare-native staging backend. It owns authenticated chat history and generation in a per-account Durable Object, uses Workers AI for generation, and serves truthful empty projections for retained domains that do not yet have Cloudflare storage adapters. Run `bun run --cwd apps/backend-worker deploy:dry-run` before `deploy:staging`. The `API_TOKEN` secret is provisioned only through Wrangler.
