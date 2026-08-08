import { GENERATION } from './constants.mjs';

/**
 * @typedef {{ name: string, ok: boolean, servedRequests: number, failure?: string }} DomainRecord
 * @typedef {{ generation: 'legacy', baseUrl: string, domains: DomainRecord[] }} LegacyReport
 */

/**
 * @param {{ baseUrl: string, domains: DomainRecord[] }} input
 * @returns {LegacyReport}
 */
export function buildLegacyReport(input) {
  return {
    generation: GENERATION,
    baseUrl: input.baseUrl,
    domains: input.domains.map((domain) => ({
      generation: GENERATION,
      name: domain.name,
      ok: domain.ok,
      servedRequests: domain.servedRequests,
      ...(domain.failure ? { failure: domain.failure } : {}),
    })),
  };
}

/**
 * @param {LegacyReport} report
 */
export function assertNotNewStack(report) {
  if (!report || typeof report !== 'object') {
    throw new Error('report must be an object');
  }
  if (report.generation !== GENERATION) {
    throw new Error(
      `refusing to treat generation:${String(report.generation)} report as legacy-wire evidence`,
    );
  }
  for (const domain of report.domains ?? []) {
    if (domain.generation !== GENERATION) {
      throw new Error(
        `domain ${domain.name ?? '<unknown>'} is not stamped generation:${GENERATION}`,
      );
    }
  }
}

/**
 * Reject decorative green: ok domains must have served real traffic.
 *
 * @param {LegacyReport} report
 */
export function assertServedTraffic(report) {
  assertNotNewStack(report);

  if (!report.baseUrl || typeof report.baseUrl !== 'string') {
    throw new Error('legacy report missing baseUrl server identity');
  }

  let totalServed = 0;
  for (const domain of report.domains) {
    if (domain.ok && domain.servedRequests === 0) {
      throw new Error(
        `domain ${domain.name} reported ok:true with servedRequests:0 — stall indistinguishable from working`,
      );
    }
    totalServed += domain.servedRequests;
  }

  if (totalServed === 0) {
    throw new Error('legacy probe served zero domain requests across all domains');
  }
}

/**
 * @param {LegacyReport} report
 * @returns {LegacyReport}
 */
export function finalizeLegacyReport(report) {
  assertServedTraffic(report);
  const allOk = report.domains.every((domain) => domain.ok);
  if (!allOk) {
    const failed = report.domains.filter((domain) => !domain.ok).map((domain) => domain.name);
    throw new Error(`legacy domains failed: ${failed.join(', ')}`);
  }
  return report;
}
