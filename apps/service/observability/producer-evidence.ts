import { AsyncLocalStorage } from "node:async_hooks";

/** Host-owned QA metadata. Product bodies and queries never supply attribution. */
export const QA_CLIENT_ID_HEADER = "x-omi-client-id";
export const QA_RUN_ID_HEADER = "x-omi-run-id";

export const QA_EVIDENCE_SHELLS = Object.freeze(["macos", "ios"] as const);
export const QA_EVIDENCE_DOMAINS = Object.freeze([
  "memories",
  "tasks",
  "conversations",
  "folders",
  "listen",
  "chat",
  "settings",
] as const);

export type QaEvidenceShell = typeof QA_EVIDENCE_SHELLS[number];
export type QaEvidenceDomain = typeof QA_EVIDENCE_DOMAINS[number];

export interface QaEvidenceIdentity {
  readonly runId: string;
  readonly shell: QaEvidenceShell;
}

export interface QaProducerEvidenceRow {
  readonly runId: string;
  readonly shell: QaEvidenceShell;
  readonly domain: QaEvidenceDomain;
  readonly evidence: "served-outcome";
  readonly http?: { readonly successful: number };
  readonly chat?: { readonly acceptedAdmission: number };
  readonly listen?: {
    readonly protocolReady: number;
    readonly acceptedBinary: number;
    readonly acceptedBinaryBytes: number;
  };
}

export interface QaProducerEvidenceDocument {
  readonly schema: "omi.producer-evidence.v1";
  readonly runId: string;
  readonly rows: readonly QaProducerEvidenceRow[];
}

export interface QaProducerEvidence {
  readonly withRequestIdentity: <Value>(
    headers: {
      readonly clientId: string | null | undefined;
      readonly runId: string | null | undefined;
    },
    operation: () => Value,
  ) => Value;
  readonly resolveIdentity: (headers: {
    readonly clientId: string | null | undefined;
    readonly runId: string | null | undefined;
  }) => QaEvidenceIdentity | null;
  readonly recordHttpSuccess: (domain: Exclude<QaEvidenceDomain, "listen">) => void;
  readonly recordAcceptedAdmission: () => void;
  readonly recordProtocolReady: (identity: QaEvidenceIdentity | null) => void;
  readonly recordAcceptedBinary: (
    identity: QaEvidenceIdentity | null,
    byteLength: number,
  ) => void;
  readonly snapshot: (runId: string) => QaProducerEvidenceDocument;
  readonly reset: () => void;
}

const RUN_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$/;
const MAX_RUNS = 32;
const MAX_COUNT = Number.MAX_SAFE_INTEGER;
const SHELLS: ReadonlySet<string> = new Set(QA_EVIDENCE_SHELLS);

export const isQaEvidenceRunId = (value: unknown): value is string =>
  typeof value === "string"
  && RUN_ID.test(value)
  && !value.startsWith("__")
  && value !== "anonymous"
  && value !== "overflow";

const asShell = (value: string): QaEvidenceShell | null =>
  SHELLS.has(value) ? value as QaEvidenceShell : null;

/**
 * Accepts the existing shell-owned combined client id (`run::shell`) and the
 * explicit two-header form (`x-omi-run-id: run`, `x-omi-client-id: shell`). If
 * both headers are present they must resolve to the same run. Header folding,
 * reserved buckets and whitespace are rejected rather than normalized.
 */
export const resolveQaEvidenceIdentity = (headers: {
  readonly clientId: string | null | undefined;
  readonly runId: string | null | undefined;
}): QaEvidenceIdentity | null => {
  const clientId = headers.clientId;
  const rawRunId = headers.runId;
  if (typeof clientId !== "string" || clientId.length === 0 || clientId.includes(",")) {
    return null;
  }
  if (rawRunId !== null && rawRunId !== undefined) {
    if (!isQaEvidenceRunId(rawRunId) || rawRunId.includes(",")) return null;
    const explicitShell = asShell(clientId);
    if (explicitShell !== null) return Object.freeze({ runId: rawRunId, shell: explicitShell });
  }

  const separator = clientId.indexOf("::");
  if (separator < 1 || separator !== clientId.lastIndexOf("::")) return null;
  const combinedRunId = clientId.slice(0, separator);
  const shell = asShell(clientId.slice(separator + 2));
  if (!isQaEvidenceRunId(combinedRunId) || shell === null) return null;
  if (rawRunId !== null && rawRunId !== undefined && rawRunId !== combinedRunId) return null;
  return Object.freeze({ runId: combinedRunId, shell });
};

interface MutableTally {
  httpSuccessful: number;
  acceptedAdmission: number;
  protocolReady: number;
  acceptedBinary: number;
  acceptedBinaryBytes: number;
}

const coordinateKey = (shell: QaEvidenceShell, domain: QaEvidenceDomain): string =>
  `${shell}/${domain}`;

const increment = (value: number, amount = 1): number => {
  if (!Number.isSafeInteger(amount) || amount < 0 || value > MAX_COUNT - amount) {
    throw new TypeError("QA producer evidence count would exceed Number.MAX_SAFE_INTEGER");
  }
  return value + amount;
};

const emptyTally = (): MutableTally => ({
  httpSuccessful: 0,
  acceptedAdmission: 0,
  protocolReady: 0,
  acceptedBinary: 0,
  acceptedBinaryBytes: 0,
});

export const createQaProducerEvidence = (): QaProducerEvidence => {
  const requestIdentity = new AsyncLocalStorage<QaEvidenceIdentity | null>();
  const runs = new Map<string, Map<string, MutableTally>>();

  const tallyFor = (
    identity: QaEvidenceIdentity,
    domain: QaEvidenceDomain,
  ): MutableTally | null => {
    let run = runs.get(identity.runId);
    if (run === undefined) {
      if (runs.size >= MAX_RUNS) return null;
      run = new Map();
      runs.set(identity.runId, run);
    }
    const key = coordinateKey(identity.shell, domain);
    let tally = run.get(key);
    if (tally === undefined) {
      tally = emptyTally();
      run.set(key, tally);
    }
    return tally;
  };

  return Object.freeze({
    withRequestIdentity<Value>(headers, operation: () => Value): Value {
      return requestIdentity.run(resolveQaEvidenceIdentity(headers), operation);
    },

    resolveIdentity: resolveQaEvidenceIdentity,

    recordHttpSuccess(domain): void {
      const identity = requestIdentity.getStore();
      if (identity === undefined || identity === null) return;
      const tally = tallyFor(identity, domain);
      if (tally !== null) tally.httpSuccessful = increment(tally.httpSuccessful);
    },

    recordAcceptedAdmission(): void {
      const identity = requestIdentity.getStore();
      if (identity === undefined || identity === null) return;
      const tally = tallyFor(identity, "chat");
      if (tally !== null) tally.acceptedAdmission = increment(tally.acceptedAdmission);
    },

    recordProtocolReady(identity): void {
      if (identity === null) return;
      const tally = tallyFor(identity, "listen");
      if (tally !== null) tally.protocolReady = increment(tally.protocolReady);
    },

    recordAcceptedBinary(identity, byteLength): void {
      if (identity === null || !Number.isSafeInteger(byteLength) || byteLength <= 0) return;
      const tally = tallyFor(identity, "listen");
      if (tally === null) return;
      tally.acceptedBinary = increment(tally.acceptedBinary);
      tally.acceptedBinaryBytes = increment(tally.acceptedBinaryBytes, byteLength);
    },

    snapshot(runId): QaProducerEvidenceDocument {
      if (!isQaEvidenceRunId(runId)) throw new TypeError("invalid QA evidence run id");
      const run = runs.get(runId);
      const rows = QA_EVIDENCE_SHELLS.flatMap((shell) => QA_EVIDENCE_DOMAINS.map((domain) => {
        const tally = run?.get(coordinateKey(shell, domain)) ?? emptyTally();
        const base = {
          runId,
          shell,
          domain,
          evidence: "served-outcome" as const,
        };
        if (domain === "listen") {
          return Object.freeze({
            ...base,
            listen: Object.freeze({
              protocolReady: tally.protocolReady,
              acceptedBinary: tally.acceptedBinary,
              acceptedBinaryBytes: tally.acceptedBinaryBytes,
            }),
          });
        }
        if (domain === "chat") {
          return Object.freeze({
            ...base,
            http: Object.freeze({ successful: tally.httpSuccessful }),
            chat: Object.freeze({ acceptedAdmission: tally.acceptedAdmission }),
          });
        }
        return Object.freeze({
          ...base,
          http: Object.freeze({ successful: tally.httpSuccessful }),
        });
      }));
      return Object.freeze({
        schema: "omi.producer-evidence.v1",
        runId,
        rows: Object.freeze(rows),
      });
    },

    reset(): void {
      runs.clear();
    },
  });
};
