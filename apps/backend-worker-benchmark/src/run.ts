import { buildSyntheticCorpus, validateCorpusRaw } from "./corpus";
import { runWorkload } from "./harness";
import { evaluateGates } from "./gates";
import { aggregateMetrics } from "./metrics";
import { createVectorizeProvider } from "./providers/vectorize";
import { createAISearchProvider } from "./providers/aisearch";
import { createBadProvider } from "./providers/bad";
import type { RetrievalProvider, RetrievalMetrics } from "./types";

type ProviderReport = {
  readonly name: string;
  readonly gatePassed: boolean;
  readonly gateReasons: readonly string[];
  readonly metrics: RetrievalMetrics;
};

const accountDocs = (
  docs: ReturnType<typeof buildSyntheticCorpus>["docs"]
): Map<string, ReadonlySet<string>> => {
  const merged = new Map<string, ReadonlySet<string>>();
  for (const doc of docs) {
    const existing = merged.get(doc.accountId) ?? new Set<string>();
    const next = new Set<string>(existing);
    next.add(doc.id);
    merged.set(doc.accountId, next);
  }
  return merged;
};

const reportFor = async (
  provider: RetrievalProvider
): Promise<ProviderReport> => {
  const corpus = buildSyntheticCorpus();
  const { samples } = await runWorkload(provider, corpus, {
    k: 5,
    deleteCount: 2,
  });
  const gates = evaluateGates(samples, accountDocs(corpus.docs));
  const metrics = aggregateMetrics(samples, 5);
  return {
    name: provider.name,
    gatePassed: gates.passed,
    gateReasons: gates.passed ? [] : gates.reasons,
    metrics,
  };
};

const format = (n: number, digits = 3): string => n.toFixed(digits);

const printReport = (report: ProviderReport): void => {
  const m = report.metrics;
  console.log(`\n== ${report.name} ==`);
  console.log(`  gate:        ${report.gatePassed ? "PASS" : "FAIL"}`);
  if (!report.gatePassed) {
    for (const reason of report.gateReasons) console.log(`    - ${reason}`);
  }
  console.log(`  recall@5:    ${format(m.recallAtK)}`);
  console.log(`  mrr:         ${format(m.mrr)}`);
  console.log(`  ndcg:        ${format(m.ndcg)}`);
  console.log(
    `  latency ms:  p50=${format(m.latency.p50)} p95=${format(
      m.latency.p95
    )} p99=${format(m.latency.p99)}`
  );
  console.log(
    `  index lag:   p50=${format(m.indexLag.p50)} p95=${format(
      m.indexLag.p95
    )} p99=${format(m.indexLag.p99)}`
  );
};

const main = async (): Promise<void> => {
  const corpus = buildSyntheticCorpus();
  const validation = validateCorpusRaw(corpus.docs, corpus.queries);
  if (!validation.ok) {
    console.error("corpus validation failed:");
    for (const reason of validation.reasons) console.error(`  - ${reason}`);
    process.exit(1);
  }

  const reports: ProviderReport[] = [];
  for (const provider of [
    createVectorizeProvider(),
    createAISearchProvider(),
    createBadProvider(),
  ]) {
    reports.push(await reportFor(provider));
  }

  console.log(
    "Synthetic retrieval benchmark (local, no network, no credentials)"
  );
  console.log(
    "Providers: Cloudflare Vectorize vs AI Search (in-memory simulations)"
  );
  for (const report of reports) printReport(report);

  const anyGoodGateFail = reports
    .filter((r) => r.name !== "intentionally-bad")
    .some((r) => !r.gatePassed);
  if (anyGoodGateFail) {
    console.error(
      "\nA candidate provider failed a hard gate. No selection made."
    );
    process.exit(2);
  }
  const badFailed =
    reports.find((r) => r.name === "intentionally-bad")?.gatePassed === false;
  console.log(
    `\nGate sensitivity self-check: ${
      badFailed ? "PASS (bad provider correctly rejected)" : "FAIL"
    }`
  );
  console.log(
    "\nNo provider is selected by this local run. A real Cloudflare staging run on synthetic staging resources is required before claiming a winner (see README.md)."
  );
};

void main();
