import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

// Ship mode serves dist/ from the shell's origin (ADR-009: interception on
// mobile, loopback on macOS) — relative base so assets resolve anywhere.

const HERE = dirname(fileURLToPath(import.meta.url));
const LISTEN_PROTOCOL_SCHEMA = readFileSync(
  join(HERE, "../../contracts/wire/listen/listen-protocol.schema.json"),
  "utf8",
);

/**
 * Stamps this build with the source tree it was built from (integration/lib/provenance.mjs).
 *
 * Why: the false-greens this exists to catch ("the artifact I measured is not the
 * artifact I edited") happen precisely when a `dist/` is stale relative to the working
 * tree and nothing says so. The stamp closes that gap two ways — `__OMI_BUILD_STAMP__`
 * for anything that can run the bundle (main.tsx reads it into runtime state), and
 * `dist/omi-build-stamp.json` for anything that can't: the L2 lane checks dist freshness
 * from plain node, without booting a browser.
 *
 * A build must never fail because provenance failed — git being unavailable (a tarball
 * checkout, a shallow CI clone missing objects) is a real, survivable case, not a build
 * error. On failure the stamp is a distinguishable `unavailable` object, never a made-up
 * value that merely looks like a valid one: an invented-but-plausible stamp is exactly
 * the failure class this mechanism exists to eliminate.
 *
 * The stamp is computed once, in the `config` hook — which Vite resolves BEFORE
 * `buildStart`, and which is the last point `define` can still be changed. Computing it
 * later (e.g. in `buildStart`) would leave `__OMI_BUILD_STAMP__` frozen at whatever
 * `define` already held, i.e. undefined.
 */
function buildProvenancePlugin(): Plugin {
  let stamp: Record<string, unknown> = {
    schema: 1,
    repo: "core-foundation",
    artifact: "surfaces-dist",
    unavailable: "provenance plugin did not run",
  };
  return {
    name: "omi-build-provenance",
    async config() {
      try {
        const { worktreeStamp } = await import("../../../integration/lib/provenance.mjs");
        stamp = worktreeStamp({ repo: "core-foundation", artifact: "surfaces-dist" });
      } catch (error) {
        stamp = {
          schema: 1,
          repo: "core-foundation",
          artifact: "surfaces-dist",
          unavailable: error instanceof Error ? error.message : String(error),
        };
      }
      return { define: { __OMI_BUILD_STAMP__: JSON.stringify(stamp) } };
    },
    async closeBundle() {
      // Guarded for the same reason `config` is, and it is not symmetry for its
      // own sake: if the module could not be imported above, this import fails
      // too, and an UNGUARDED failure here turns "provenance unavailable" into
      // "the build is broken" — the one outcome the fallback above exists to
      // prevent. Write the file by hand in that case so the stale-dist check
      // still finds an honest `unavailable` marker rather than nothing at all
      // (absent and unavailable are different findings; only one of them means
      // someone deleted the stamp).
      try {
        const { writeStampFile } = await import("../../../integration/lib/provenance.mjs");
        writeStampFile(join(HERE, "dist", "omi-build-stamp.json"), stamp);
      } catch (error) {
        writeFileSync(
          join(HERE, "dist", "omi-build-stamp.json"),
          `${JSON.stringify({ ...stamp, unavailable: error instanceof Error ? error.message : String(error) }, null, 2)}\n`,
        );
      }
    },
  };
}

export default defineConfig({
  base: "./",
  plugins: [react(), buildProvenancePlugin()],
  define: {
    __OMI_LISTEN_PROTOCOL_SCHEMA__: JSON.stringify(LISTEN_PROTOCOL_SCHEMA),
  },
  build: { outDir: "dist", sourcemap: true },
});
