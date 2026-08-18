import type { AccountScope, MetricSample, RetrievalProvider } from "./types";
import type { SyntheticCorpus } from "./corpus";

export type WorkloadOptions = {
  readonly k: number;
  readonly deleteCount: number;
};
export type WorkloadResult = {
  readonly samples: readonly MetricSample[];
  readonly revokedIds: ReadonlySet<string>;
};

const scopeDocs = (corpus: SyntheticCorpus, scope: AccountScope) =>
  corpus.docs.filter((doc) => doc.accountId === scope.accountId);

const scopeQueries = (corpus: SyntheticCorpus, scope: AccountScope) =>
  corpus.queries.filter((query) => query.accountId === scope.accountId);

const EMPTY_REVOKED: ReadonlySet<string> = new Set();

export const runWorkload = async (
  provider: RetrievalProvider,
  corpus: SyntheticCorpus,
  options: WorkloadOptions
): Promise<WorkloadResult> => {
  const samples: MetricSample[] = [];
  const revokedIds = new Set<string>();

  for (const scope of corpus.scopes) {
    const docs = scopeDocs(corpus, scope);
    const queries = scopeQueries(corpus, scope);

    for (const doc of docs) await provider.upsert(scope, doc);
    for (const query of queries) {
      const result = await provider.query(scope, query, options.k);
      samples.push({
        queryId: `${query.id}#lag`,
        scope,
        relevantDocIds: query.relevantDocIds,
        hits: result.hits,
        latencyMs: result.latencyMs,
        indexLagMs: provider.pendingLagMs(scope),
        revokedIdsAtQueryTime: EMPTY_REVOKED,
      });
    }
    await provider.flush(scope);

    for (const query of queries) {
      const result = await provider.query(scope, query, options.k);
      samples.push({
        queryId: `${query.id}#steady`,
        scope,
        relevantDocIds: query.relevantDocIds,
        hits: result.hits,
        latencyMs: result.latencyMs,
        indexLagMs: provider.pendingLagMs(scope),
        revokedIdsAtQueryTime: EMPTY_REVOKED,
      });
    }

    const toDelete = docs.slice(0, options.deleteCount);
    for (const doc of toDelete) {
      await provider.delete(scope, doc.id);
      revokedIds.add(doc.id);
    }
    await provider.flush(scope);
    const revokedAtQueryTime: ReadonlySet<string> = new Set(revokedIds);
    for (const query of queries) {
      const result = await provider.query(scope, query, options.k);
      samples.push({
        queryId: `${query.id}#postdelete`,
        scope,
        relevantDocIds: query.relevantDocIds,
        hits: result.hits,
        latencyMs: result.latencyMs,
        indexLagMs: provider.pendingLagMs(scope),
        revokedIdsAtQueryTime: revokedAtQueryTime,
      });
    }
  }

  return { samples, revokedIds };
};
