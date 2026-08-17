/**
 * Score one boundary prompt version against another by replaying already-decided
 * provisional claims out of a finished (or in-flight) run db.
 *
 * The point is to tune promote taste without paying for a full rebuild: a run
 * takes ~12h, while replaying a few dozen labelled claims through both prompt
 * versions takes minutes and answers the only question that matters — does the
 * new version recover the durable owner facts the old one dropped, without also
 * admitting the session residue the old one correctly dropped.
 *
 *   bun run harness/boundary-probe.ts <db> --labels <labels.json> [--versions v4,v5]
 *                                     [--concurrency 2] [--model glm|codex]
 *
 * labels.json is `[{ "claim_revision_id": "...", "expect": "accept_ltm"|"abstain",
 * "note": "..." }]`. It lives outside this repo (it quotes real personal data);
 * only its path is passed in, so no private path literal enters platform/.
 */
import { Database } from "bun:sqlite";
import type { Evidence, ProvisionalClaim } from "../core/schema";
import { invokeUnitBoundaryStrategy } from "../drivers/model/unit-boundary-edge";
import { selectModel } from "./model-select";
import type { ModelPort } from "../drivers/model/port";

type Expect = "accept_ltm" | "abstain";
type Label = { claim_revision_id: string; expect: Expect; note?: string };
type Outcome = { label: Label; predicate: string; decision: Expect | "error"; reason?: string };

const arg = (flag: string, fallback?: string): string | undefined => {
  const index = process.argv.indexOf(flag);
  return index >= 0 ? process.argv[index + 1] : fallback;
};

/** The db stores claims and evidence as opaque content_json; the boundary edge
 * needs the same shapes the pipeline handed it, so rebuild them verbatim. */
const loadClaims = (db: Database, ids: readonly string[]) => {
  const claims = new Map<string, ProvisionalClaim>();
  const statement = db.query<{ content_json: string }, [string]>("SELECT content_json FROM claim_revisions WHERE revision_id = ?");
  for (const id of ids) {
    const row = statement.get(id);
    if (row) claims.set(id, JSON.parse(row.content_json) as ProvisionalClaim);
  }
  return claims;
};

const loadEvidence = (db: Database): Map<string, Evidence> => {
  const byId = new Map<string, Evidence>();
  for (const row of db.query<{ content_json: string }, []>("SELECT content_json FROM evidence_revisions").all()) {
    const evidence = JSON.parse(row.content_json) as Evidence;
    byId.set(evidence.evidence_id, evidence);
  }
  return byId;
};

const mapLimit = async <T, R>(items: readonly T[], limit: number, run: (item: T) => Promise<R>): Promise<R[]> => {
  const results = new Array<R>(items.length);
  let next = 0;
  await Promise.all(Array.from({ length: Math.max(1, Math.min(limit, items.length)) }, async () => {
    for (let index = next++; index < items.length; index = next++) results[index] = await run(items[index]!);
  }));
  return results;
};

/** Version is selected by env inside invokeUnitBoundaryStrategy, so each sweep
 * sets it around its own calls. Sweeps therefore run one after another. */
const sweep = async (version: string, model: ModelPort, work: readonly { label: Label; claim: ProvisionalClaim; evidence: Evidence[] }[], concurrency: number): Promise<Outcome[]> => {
  const previous = process.env.OMI_BOUNDARY_VERSION;
  process.env.OMI_BOUNDARY_VERSION = version;
  try {
    return await mapLimit(work, concurrency, async ({ label, claim, evidence }) => {
      try {
        const judged = await invokeUnitBoundaryStrategy(model, claim, evidence);
        return { label, predicate: claim.predicate, decision: judged.decision, ...(judged.decision === "abstain" ? { reason: judged.reason } : {}) };
      } catch (error) {
        // An error is not an abstention: recording it as one would silently
        // credit a version for a decision it never made.
        return { label, predicate: claim.predicate, decision: "error" as const, reason: error instanceof Error ? error.message : String(error) };
      }
    });
  } finally {
    if (previous === undefined) delete process.env.OMI_BOUNDARY_VERSION;
    else process.env.OMI_BOUNDARY_VERSION = previous;
  }
};

const report = (version: string, outcomes: readonly Outcome[]) => {
  const durable = outcomes.filter((outcome) => outcome.label.expect === "accept_ltm");
  const residue = outcomes.filter((outcome) => outcome.label.expect === "abstain");
  const kept = durable.filter((outcome) => outcome.decision === "accept_ltm").length;
  const dropped = residue.filter((outcome) => outcome.decision === "abstain").length;
  const errors = outcomes.filter((outcome) => outcome.decision === "error").length;
  const pct = (n: number, d: number) => d ? `${((n / d) * 100).toFixed(1)}%` : "n/a";
  console.log(`\n=== ${version}`);
  console.log(`  recall on durable facts : ${kept}/${durable.length} (${pct(kept, durable.length)})`);
  console.log(`  residue correctly held  : ${dropped}/${residue.length} (${pct(dropped, residue.length)})`);
  console.log(`  errors                  : ${errors}`);
  const unjustified = outcomes.filter((outcome) => outcome.decision === "abstain" && (!outcome.reason || outcome.reason === "GLM boundary sufficiency abstention")).length;
  console.log(`  abstentions w/o reason  : ${unjustified}`);
  return { version, kept, durable: durable.length, dropped, residue: residue.length, errors, unjustified };
};

const main = async () => {
  const dbPath = process.argv[2];
  const labelsPath = arg("--labels");
  if (!dbPath || dbPath.startsWith("--") || !labelsPath) {
    console.error("usage: bun run harness/boundary-probe.ts <db> --labels <labels.json> [--versions v4,v5] [--concurrency 2] [--model glm]");
    process.exit(2);
  }
  const versions = (arg("--versions", "v4,v5") ?? "v4,v5").split(",").map((entry) => entry.trim()).filter(Boolean);
  const concurrency = Number(arg("--concurrency", "2"));
  const selection = selectModel(process.argv, "boundary-probe");
  if (!selection.live) throw new Error("boundary-probe scores a real prompt: pass --model glm or --model codex");
  const model = selection.model;
  const started = Date.now();

  const labels = JSON.parse(await Bun.file(labelsPath).text()) as Label[];
  const db = new Database(dbPath, { readonly: true });
  const claims = loadClaims(db, labels.map((label) => label.claim_revision_id));
  const evidenceById = loadEvidence(db);

  const work = labels.flatMap((label) => {
    const claim = claims.get(label.claim_revision_id);
    if (!claim) return [];
    const evidence = claim.evidence_refs.flatMap((id) => {
      const item = evidenceById.get(id);
      return item?.excerpt ? [item] : [];
    });
    // buildUnitBoundaryRequest throws without a retained excerpt; skipping here
    // keeps a corpus gap from being scored as a model failure.
    return evidence.length ? [{ label, claim, evidence }] : [];
  });
  console.log(`labelled=${labels.length} replayable=${work.length} durable=${work.filter((entry) => entry.label.expect === "accept_ltm").length} residue=${work.filter((entry) => entry.label.expect === "abstain").length}`);

  const summaries = [];
  const byVersion = new Map<string, Outcome[]>();
  for (const version of versions) {
    const outcomes = await sweep(version, model, work, concurrency);
    byVersion.set(version, outcomes);
    summaries.push(report(version, outcomes));
  }

  // The per-item flips are the actionable part: which durable facts a version
  // recovered, and which residue it started letting through.
  if (versions.length === 2) {
    const [before, after] = versions as [string, string];
    const a = byVersion.get(before)!;
    const b = byVersion.get(after)!;
    console.log(`\n=== flips ${before} -> ${after}`);
    for (let index = 0; index < a.length; index += 1) {
      const from = a[index]!;
      const to = b[index]!;
      if (from.decision === to.decision) continue;
      const good = to.decision === from.label.expect;
      console.log(`  ${good ? "FIXED  " : "REGRESS"} [${from.label.expect}] ${from.predicate}: ${from.decision} -> ${to.decision}${to.reason ? ` (${to.reason})` : ""}`);
    }
  }
  const elapsed_s = Math.round((Date.now() - started) / 100) / 10;
  // Reported whenever OMI_VERDICT_CACHE is set, so a cold/warm pair is directly
  // comparable: same labels, same versions, only the cache differs.
  const stats = (model as { stats?: { hits: number; misses: number; writes: number } }).stats;
  if (stats) {
    const total = stats.hits + stats.misses;
    console.log(`\ncache: hits=${stats.hits} misses=${stats.misses} writes=${stats.writes} hit_rate=${total ? ((stats.hits / total) * 100).toFixed(1) : "0.0"}%`);
  }
  console.log(`wall_clock_s: ${elapsed_s}`);
  console.log(`\n${JSON.stringify(summaries)}`);
  db.close();
};

await main();
