import type { MetricSample } from "./types";

export type GateResult =
  | { passed: true }
  | { passed: false; reasons: string[] };

export const evaluateGates = (
  samples: readonly MetricSample[],
  accountDocs: ReadonlyMap<string, ReadonlySet<string>>
): GateResult => {
  const reasons: string[] = [];
  for (const sample of samples) {
    const allowed = accountDocs.get(sample.scope.accountId);
    for (const hit of sample.hits) {
      if (allowed === undefined || !allowed.has(hit.id)) {
        reasons.push(
          `query ${sample.queryId} returned foreign id ${hit.id} for scope ${sample.scope.accountId}`
        );
      }
      if (sample.revokedIdsAtQueryTime.has(hit.id)) {
        reasons.push(`query ${sample.queryId} returned revoked id ${hit.id}`);
      }
    }
  }
  if (reasons.length === 0) return { passed: true };
  return { passed: false, reasons };
};
