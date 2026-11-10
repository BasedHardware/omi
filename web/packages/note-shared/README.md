# @omi/note-shared

Internal ESM source package for note citation repair and transcript source IDs.
The signed-in app (Bun) and public frontend (npm) each depend on
`file:../packages/note-shared` through their own lockfile; there is no root workspace
or package build step. Import the two entries through the package exports:

- `@omi/note-shared/note-citations.mjs`
- `@omi/note-shared/note-sources.mjs`

Each entry exposes its `.d.mts` types. `note-sources.mjs` also carries the display
helpers every client uses: `presentableNoteSection` (repair a section and promote the
inline citations it removed to source IDs, as macOS `presentableSection` does),
`presentableNoteText` (titles, action items, events) and `noteTranscriptIDs`.

The Windows/Linux desktop app (`desktop/windows`) bundles this package from source
through a Vite/TypeScript alias rather than a lockfile dependency; its CI triggers on
`web/packages/note-shared/**`. The language-neutral fixture remains at
`contracts/note_citation_contract.json`.

Both Dockerfiles copy this package into the dependency-install stage. Bun 1.3.14 installs
a directory of per-file symlinks, so the app also carries the dependency target
from the install stage into the builder and production install. The frontend's `.npmrc` sets `install-links=true` so npm packs the
local dependency into `node_modules`; a symlink outside the frontend's pinned Next
root fails Turbopack resolution. After package edits, reinstall consumer dependencies
(`bun install` in `web/app`, `npm ci` in `web/frontend`) before running checks.
