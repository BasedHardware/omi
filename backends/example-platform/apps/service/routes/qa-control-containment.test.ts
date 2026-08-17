/**
 * CONTAINMENT — who is allowed to compose the dev control plane.
 *
 * `routes/qa-control.ts` lets an authenticated caller `observe` and `activate`
 * **its own account's** control state. In a QA fixture that is the point: R3
 * rules that the local stack may seed dev accounts so the epoch fence can admit
 * anything at all, because nothing in `platform` mints control state and every
 * account otherwise denies `control_state_absent`.
 *
 * Behind a real credential seam the same routes are self-service epoch
 * activation. `backend:ADR-010` §1 puts control state under LEGACY's authority
 * and the fence exists so a client cannot decide its own generation, epoch or
 * activation; these routes would let any user walk their own account through
 * `legacy -> migrating -> new`, activate an epoch, and have the fence admit
 * writes it was built to deny — answering honestly, about state the caller
 * wrote.
 *
 * ── WHY A TEST AND NOT A COMMENT ─────────────────────────────────────────────
 *
 * Because the property is about a set of files, and a comment cannot notice the
 * file that joins it. The measured state of the tree today is that containment
 * is **intended and unenforced**: exactly one composition site, and nothing
 * standing between a future one and these routes. There is no production server
 * composition in this repository at all, so nothing can reach them right now —
 * which is a fact about the current tree, not a property of the module, and it
 * will stop being true.
 *
 * ── WHAT THIS CHECK IS, PRECISELY ────────────────────────────────────────────
 *
 * A containment check, not a capability restriction. It cannot stop anyone from
 * composing these routes; it makes doing so a **visible diff in a file whose
 * only job is to say who may** — the same shape `WIRE_PATH_REGISTRY` uses for
 * wire paths, and the same reasoning: a registry that must be edited is a
 * ratchet, where a convention that must be remembered is not.
 *
 * It is a new guard, so per swarm-protocol §8 it is PROVISIONAL until a
 * non-author has read it against the English statement above and audited its
 * false positives. Its own known limits, named now rather than discovered:
 *
 * - It matches an IMPORT and a CALL by name on comment-stripped text. A caller
 *   reaching the module through `await import()` with a computed specifier, or
 *   through a re-export under a different name, is invisible to it.
 * - It says nothing about whether the ONE allowed composition is itself safe.
 *   That `app-facing.ts` is a QA fixture is asserted by its own tests (in-memory
 *   SQLite, dev tokens, a seeded corpus), not here.
 */

import { describe, expect, test } from "bun:test";
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";

/**
 * The one file allowed to compose the dev control plane. Adding to this list is
 * the visible diff the check exists to force — and if you are adding one, the
 * module header of `qa-control.ts` is the thing to read first.
 */
const ALLOWED_COMPOSITION_SITES = ["apps/service/app-facing.ts"] as const;

/** Same exemption rule the import fence uses: prose cannot compose anything. */
const withoutComments = (text: string): string => text
  .replace(/\/\*[\s\S]*?\*\//g, (match) => match.replace(/[^\n]/g, " "))
  .replace(/(^|[^:])\/\/[^\n]*/g, (match, lead: string) => lead + " ".repeat(match.length - lead.length));

const platformRoot = new URL("../../..", import.meta.url).pathname;

const sourceFiles = (directory: string): string[] =>
  readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    if (entry.isDirectory()) {
      return entry.name === "node_modules" || entry.name === ".git"
        ? []
        : sourceFiles(join(directory, entry.name));
    }
    return /\.tsx?$/.test(entry.name) ? [join(directory, entry.name)] : [];
  });

describe("the dev control plane has exactly one composition site", () => {
  /**
   * red-proof: add an import of `routes/qa-control` AND a
   * `registerQaControlRoutes(app, …)` call to a second file — applied to
   * `integration/control/live-service.ts`. APPLIED AND OBSERVED RED, naming
   * that file.
   *
   * A WEAKER MUTATION STAYED GREEN AND IS WORTH THE SPACE: importing the module
   * and binding the symbol WITHOUT calling it (`const x =
   * registerQaControlRoutes;`) does not trip this. That is the intended
   * boundary — holding a reference composes nothing — but it is also the honest
   * limit: this check catches a call site, not reachability. A file that
   * imported the symbol and called it through an alias would be invisible, and
   * that is named here rather than implied.
   */
  test("no file outside the allowed list imports and calls registerQaControlRoutes", () => {
    const composers: string[] = [];
    for (const file of sourceFiles(platformRoot)) {
      const shown = relative(platformRoot, file);
      // Tests are exempt for the reason rules 16 and 17 exempt them: a test
      // composing a fixture is not a deployment, and this file itself names the
      // symbol several times.
      if (/\.test\.tsx?$/.test(shown)) continue;
      const code = withoutComments(readFileSync(file, "utf8"));
      const imports = /from\s+["'][^"']*routes\/qa-control["']/.test(code);
      const calls = /\bregisterQaControlRoutes\s*\(/.test(code);
      // The module that DECLARES the function is not a composer of it.
      if (shown === "apps/service/routes/qa-control.ts") continue;
      if (imports && calls) composers.push(shown);
    }
    expect(composers.sort()).toEqual([...ALLOWED_COMPOSITION_SITES].sort());
  });

  /**
   * The staleness half, and it is the half that matters over time: an allowed
   * row that no longer composes anything has quietly stopped meaning what it
   * says, which is how a registry disables itself. Symmetric with
   * `WIRE_PATH_REGISTRY`'s own stale-row failure.
   */
  test("every allowed site actually composes it, so no row silently goes stale", () => {
    for (const allowed of ALLOWED_COMPOSITION_SITES) {
      const code = withoutComments(readFileSync(join(platformRoot, allowed), "utf8"));
      expect({ allowed, composes: /\bregisterQaControlRoutes\s*\(/.test(code) })
        .toEqual({ allowed, composes: true });
    }
  });

  /**
   * The fact that makes the check load-bearing rather than decorative, asserted
   * so it cannot change quietly: the allowed site is a QA fixture service. If
   * `app-facing.ts` ever stops seeding an in-memory fixture corpus, the one
   * composition of the dev control plane has become something else and this
   * containment argument no longer holds.
   */
  test("the allowed site is a QA fixture service, not a production composition", () => {
    // CALL-SHAPED, not substring. `expect(code).toContain("seedQaSnapshot")`
    // was the first version and a red-proof renaming the seeder to
    // `seedQaSnapshotRenamed` STAYED GREEN against it — the new name contains
    // the old one. A containment claim satisfied by a prefix is not a claim.
    const code = withoutComments(readFileSync(join(platformRoot, "apps/service/app-facing.ts"), "utf8"));
    expect(/\bseedQaSnapshot\s*\(/.test(code)).toBe(true);
    expect(/\bcreateDevTokenIssuer\s*\(/.test(code)).toBe(true);
  });
});
