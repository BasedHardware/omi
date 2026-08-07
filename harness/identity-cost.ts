/**
 * Measure the identity-adjudication payload a dream cycle would build for a real
 * ledger, without calling a model.
 *
 * The fat-ledger wall is usually described as "the prompt got too big", but the
 * adjudication payload is already batched under a fixed budget, so that cannot
 * be the whole story. This reports where the per-cycle model work actually sits:
 * how many mentions survive blocking, how many batches the budget produces, and
 * -- the part no budget bounds today -- how many groups the second and third
 * phases would then visit one call at a time.
 *
 *   bun run harness/identity-cost.ts <db> [--owner <id>] [--budget 24000]
 *                                    [--cluster-size 16] [--json]
 */
import { Database } from "bun:sqlite";
import { SqliteLedger } from "../drivers/sqlite";
import { blockIdentityClusters, blockMentionClusters, buildReferentProfiles } from "../core/consolidate/identity";
import type { Mention } from "../core/schema";

const arg = (flag: string, fallback?: string): string | undefined => {
  const index = process.argv.indexOf(flag);
  return index >= 0 ? process.argv[index + 1] : fallback;
};

const quantiles = (values: readonly number[]) => {
  if (!values.length) return { p50: 0, p90: 0, max: 0, total: 0 };
  const sorted = [...values].sort((left, right) => left - right);
  const at = (q: number) => sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))]!;
  return { p50: at(0.5), p90: at(0.9), max: sorted[sorted.length - 1]!, total: values.reduce((sum, value) => sum + value, 0) };
};

const main = () => {
  const dbPath = process.argv[2];
  if (!dbPath || dbPath.startsWith("--")) {
    console.error("usage: bun run harness/identity-cost.ts <db> [--owner <id>] [--budget 24000] [--cluster-size 16] [--json]");
    process.exit(2);
  }
  const budget = Number(arg("--budget", "24000"));
  const maxClusterSize = Number(arg("--cluster-size", "16"));
  // Not readonly: SqliteLedger migrates on construct. Point this at a backup
  // copy, never at a db a run is writing.
  const db = new Database(dbPath);
  const ledger = new SqliteLedger(db);
  const owner = arg("--owner") ?? (db.query("SELECT owner_account_id FROM graph_heads LIMIT 1").get() as { owner_account_id: string } | null)?.owner_account_id;
  if (!owner) throw new Error("no owner in ledger");
  const snapshot = ledger.snapshot(owner);

  const mentions: readonly Mention[] = (snapshot.mentions ?? []).map((row) => row.mention);
  const claims = snapshot.claims ?? [];
  const evidence = snapshot.evidence ?? [];
  const events = snapshot.events ?? [];

  const surface = blockMentionClusters(mentions, maxClusterSize);
  const identity = blockIdentityClusters(mentions, maxClusterSize);
  const clusterKey = (cluster: readonly Mention[]): string => JSON.stringify(cluster.map((mention) => mention.mention_id).sort());
  const blockedKeys = new Set(surface.clusters.map(clusterKey));
  const blocked = [...surface.clusters, ...identity.clusters.filter((cluster) => !blockedKeys.has(clusterKey(cluster)))];

  // Same preparation the real path does: profiles per cluster, cost in JSON chars.
  const prepared = blocked
    .map((cluster) => { const profiles = buildReferentProfiles(cluster, claims, evidence, events); return { profiles, cost: JSON.stringify(profiles).length }; })
    .filter((entry) => entry.profiles.length > 1);

  const batches: (typeof prepared)[] = [];
  let current: typeof prepared = [];
  let size = 0;
  for (const entry of prepared) {
    if (current.length && size + entry.cost > budget) { batches.push(current); current = []; size = 0; }
    current.push(entry); size += entry.cost;
  }
  if (current.length) batches.push(current);

  // Would a "skip clusters that are fully resolved already" frontier reduction
  // remove anything HERE? Measure before building it.
  const boundByMention = new Map(mentions.map((mention) => [mention.mention_id, mention.entity_id !== null] as const));
  const clusterBinding = blocked.map((cluster) => {
    const bound = cluster.filter((mention) => boundByMention.get(mention.mention_id)).length;
    return { size: cluster.length, bound, unbound: cluster.length - bound };
  });
  const allBound = clusterBinding.filter((entry) => entry.unbound === 0).length;
  const anyBound = clusterBinding.filter((entry) => entry.bound > 0).length;

  const clusterCost = quantiles(prepared.map((entry) => entry.cost));
  const batchCost = quantiles(batches.map((batch) => batch.reduce((sum, entry) => sum + entry.cost, 0)));
  const batchProfiles = quantiles(batches.map((batch) => batch.reduce((sum, entry) => sum + entry.profiles.length, 0)));

  // Phase 2/3 are per-GROUP calls and no budget bounds their COUNT. The model
  // decides how many groups come back, so this is the honest upper bound the
  // structure permits: one candidate group per cluster at minimum, and a cluster
  // can yield several. Reported as clusters, which is the floor.
  const report = {
    db: dbPath,
    owner,
    mentions: mentions.length,
    mentions_with_identity_ref: mentions.filter((mention) => mention.source_identity_ref).length,
    claims: claims.length,
    evidence: evidence.length,
    surface_clusters: surface.clusters.length,
    surface_oversize_rejected: surface.oversize.length,
    surface_single_claim_rejected: surface.single_claim.length,
    identity_clusters: identity.clusters.length,
    identity_single_claim_rejected: identity.single_claim.length,
    blocked_clusters: blocked.length,
    mentions_bound_to_entity: mentions.filter((mention) => mention.entity_id !== null).length,
    clusters_fully_bound: allBound,
    clusters_with_any_bound_member: anyBound,
    over_budget_clusters: prepared.filter((entry) => entry.cost > budget).length,
    prepared_clusters: prepared.length,
    profiles_total: prepared.reduce((sum, entry) => sum + entry.profiles.length, 0),
    profile_chars_total: clusterCost.total,
    cluster_cost_chars: { p50: clusterCost.p50, p90: clusterCost.p90, max: clusterCost.max },
    batches: batches.length,
    batch_cost_chars: { p50: batchCost.p50, p90: batchCost.p90, max: batchCost.max },
    batch_profiles: { p50: batchProfiles.p50, p90: batchProfiles.p90, max: batchProfiles.max },
    // The three phases, in model calls.
    calls_phase1_adjudicate: batches.length,
    calls_phase2_verify_floor: prepared.length,
    calls_phase3_card_floor: prepared.length,
    calls_total_floor: batches.length + 2 * prepared.length,
  };

  // --digests prints the verdict-cache key input per cluster, one per line, so
  // two snapshots taken at different points in a run can be diffed to measure
  // the hit rate memoization would actually see ACROSS cycles. That is the
  // number that predicts the production benefit: a cluster which gains a single
  // mention is a different input and therefore a miss.
  if (process.argv.includes("--digests")) {
    for (const entry of prepared) console.log(new Bun.CryptoHasher("sha256").update(JSON.stringify(entry.profiles)).digest("hex"));
    db.close();
    return;
  }

  if (process.argv.includes("--json")) console.log(JSON.stringify(report, null, 2));
  else for (const [k, v] of Object.entries(report)) console.log(`  ${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`);
  db.close();
};

main();
