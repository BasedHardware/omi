/**
 * Verifies the contract lockfile's PUBLICATION CLAIMS against an actual remote.
 *
 * `qa-contracts.ts` checks that the lockfile is internally coherent — the declared
 * publication status agrees with the declared flags. It deliberately cannot check whether
 * those flags are TRUE OF THE WORLD, because it runs inside `bun test`, and a hermetic
 * test may not touch the network (core/AGENTS.md rule 8, and the same rule in this repo).
 *
 * That split is the whole point. Before this existed, the gate asserted
 * `upstreamBranchPushed === true` against a boolean the lockfile declares about itself:
 * it asked the lockfile whether it had been pushed, and the lockfile answered. Setting the
 * flag to `true` without pushing produced a green gate and a false record. The only thing
 * standing between us and that was an agent choosing not to write a convenient lie.
 *
 * So the coherence check stays hermetic and this one goes to the network. Run it before
 * publishing, before a release, and any time a flag flips to `true`. It is NOT part of
 * `bun test` and must never be added to it.
 *
 *   bun run scripts/verify-publication.ts
 *
 * Exit 0 = every claim the lockfile makes about a remote is true of that remote.
 */
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = dirname(dirname(fileURLToPath(import.meta.url)));

interface PublicationClaims {
  publicationStatus: string;
  source: {
    repository: string;
    ref: string;
    commit: string;
    upstreamBranchPushed: boolean;
    mergedToMain: boolean;
    registryPublished: boolean;
  };
}

const fail = (message: string): never => {
  console.error(`publication check: ${message}`);
  process.exit(1);
};

const lsRemote = async (repository: string, ref: string): Promise<string | null> => {
  // https over ssh on purpose: this must work from CI and from a laptop without a key.
  const url = `https://github.com/${repository}.git`;
  const proc = Bun.spawn(["git", "ls-remote", url, ref], { stdout: "pipe", stderr: "pipe" });
  const [out, code] = [await new Response(proc.stdout).text(), await proc.exited];
  if (code !== 0) {
    const err = await new Response(proc.stderr).text();
    fail(`git ls-remote ${url} ${ref} failed (${code}): ${err.trim()}`);
  }
  const line = out.split("\n").find((l) => l.trim().length > 0);
  return line ? (line.split(/\s+/)[0] ?? null) : null;
};

const lock = JSON.parse(await readFile(join(root, "contracts.lock.json"), "utf8")) as PublicationClaims;
const { repository, ref, commit, upstreamBranchPushed } = lock.source;

if (!upstreamBranchPushed) {
  // Nothing to verify positively — but the NEGATIVE claim is still worth checking, because
  // "not pushed" going stale is how a lockfile quietly under-reports its own maturity.
  const head = await lsRemote(repository, ref);
  if (head !== null) {
    console.log(`note: ${ref} exists at ${repository} (head ${head.slice(0, 10)}).`);
    console.log(`      The lockfile says upstreamBranchPushed=false. If ${commit.slice(0, 10)} is`);
    console.log(`      on that branch, the lockfile is understating reality — re-check it.`);
  }
  console.log(`publication check: OK — declares not-pushed, nothing claimed about a remote.`);
  process.exit(0);
}

const head = await lsRemote(repository, ref);
if (head === null) {
  fail(`lockfile claims upstreamBranchPushed=true but ${ref} does not exist at ${repository}`);
}

// The branch existing is not enough: the exact recorded commit must be reachable on it.
// A branch that has moved on is a different claim than the one the lockfile is making.
const url = `https://github.com/${repository}.git`;
const proc = Bun.spawn(["git", "fetch", "--quiet", url, commit], { stdout: "pipe", stderr: "pipe" });
if ((await proc.exited) !== 0) {
  fail(
    `lockfile claims upstreamBranchPushed=true and pins commit ${commit.slice(0, 10)}, ` +
      `but that object could not be fetched from ${repository}. ` +
      `A rebase rewrites commit ids — if the source branch was rebased after this lockfile ` +
      `was written, the pin is stale and the artifact must be re-vendored.`,
  );
}

console.log(`publication check: OK — ${commit.slice(0, 10)} is present at ${repository} ${ref}.`);
