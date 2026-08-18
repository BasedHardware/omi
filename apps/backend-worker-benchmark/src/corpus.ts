import type { AccountScope, SyntheticDoc, SyntheticQuery } from "./types";

export const SCOPES: readonly AccountScope[] = [
  { accountId: "acct-synthetic-alpha" },
  { accountId: "acct-synthetic-beta" },
];

const alphaDocs: readonly SyntheticDoc[] = [
  {
    id: "alpha-1",
    accountId: "acct-synthetic-alpha",
    embedding: [1, 0, 0, 0],
    terms: ["alpha", "schedule"],
    revoked: false,
    synthetic: true,
  },
  {
    id: "alpha-2",
    accountId: "acct-synthetic-alpha",
    embedding: [0, 1, 0, 0],
    terms: ["alpha", "task"],
    revoked: false,
    synthetic: true,
  },
  {
    id: "alpha-3",
    accountId: "acct-synthetic-alpha",
    embedding: [0, 0, 1, 0],
    terms: ["alpha", "note"],
    revoked: false,
    synthetic: true,
  },
  {
    id: "alpha-4",
    accountId: "acct-synthetic-alpha",
    embedding: [0, 0, 0, 1],
    terms: ["alpha", "memory"],
    revoked: false,
    synthetic: true,
  },
  {
    id: "alpha-5",
    accountId: "acct-synthetic-alpha",
    embedding: [1, 1, 0, 0],
    terms: ["alpha", "schedule", "task"],
    revoked: false,
    synthetic: true,
  },
  {
    id: "alpha-6",
    accountId: "acct-synthetic-alpha",
    embedding: [0, 0, 1, 1],
    terms: ["alpha", "note", "memory"],
    revoked: false,
    synthetic: true,
  },
];

const betaDocs: readonly SyntheticDoc[] = [
  {
    id: "beta-1",
    accountId: "acct-synthetic-beta",
    embedding: [1, 0, 0, 0],
    terms: ["beta", "schedule"],
    revoked: false,
    synthetic: true,
  },
  {
    id: "beta-2",
    accountId: "acct-synthetic-beta",
    embedding: [0, 1, 0, 0],
    terms: ["beta", "task"],
    revoked: false,
    synthetic: true,
  },
  {
    id: "beta-3",
    accountId: "acct-synthetic-beta",
    embedding: [0, 0, 1, 0],
    terms: ["beta", "note"],
    revoked: false,
    synthetic: true,
  },
  {
    id: "beta-4",
    accountId: "acct-synthetic-beta",
    embedding: [0, 0, 0, 1],
    terms: ["beta", "memory"],
    revoked: false,
    synthetic: true,
  },
  {
    id: "beta-5",
    accountId: "acct-synthetic-beta",
    embedding: [1, 1, 0, 0],
    terms: ["beta", "schedule", "task"],
    revoked: false,
    synthetic: true,
  },
  {
    id: "beta-6",
    accountId: "acct-synthetic-beta",
    embedding: [0, 0, 1, 1],
    terms: ["beta", "note", "memory"],
    revoked: false,
    synthetic: true,
  },
];

const alphaQueries: readonly SyntheticQuery[] = [
  {
    id: "aq-1",
    accountId: "acct-synthetic-alpha",
    embedding: [1, 0, 0, 0],
    terms: ["schedule"],
    relevantDocIds: ["alpha-1", "alpha-5"],
  },
  {
    id: "aq-2",
    accountId: "acct-synthetic-alpha",
    embedding: [0, 1, 0, 0],
    terms: ["task"],
    relevantDocIds: ["alpha-2", "alpha-5"],
  },
  {
    id: "aq-3",
    accountId: "acct-synthetic-alpha",
    embedding: [0, 0, 1, 0],
    terms: ["note"],
    relevantDocIds: ["alpha-3", "alpha-6"],
  },
  {
    id: "aq-4",
    accountId: "acct-synthetic-alpha",
    embedding: [0, 0, 0, 1],
    terms: ["memory"],
    relevantDocIds: ["alpha-4", "alpha-6"],
  },
];

const betaQueries: readonly SyntheticQuery[] = [
  {
    id: "bq-1",
    accountId: "acct-synthetic-beta",
    embedding: [1, 0, 0, 0],
    terms: ["schedule"],
    relevantDocIds: ["beta-1", "beta-5"],
  },
  {
    id: "bq-2",
    accountId: "acct-synthetic-beta",
    embedding: [0, 1, 0, 0],
    terms: ["task"],
    relevantDocIds: ["beta-2", "beta-5"],
  },
  {
    id: "bq-3",
    accountId: "acct-synthetic-beta",
    embedding: [0, 0, 1, 0],
    terms: ["note"],
    relevantDocIds: ["beta-3", "beta-6"],
  },
  {
    id: "bq-4",
    accountId: "acct-synthetic-beta",
    embedding: [0, 0, 0, 1],
    terms: ["memory"],
    relevantDocIds: ["beta-4", "beta-6"],
  },
];

export type SyntheticCorpus = {
  readonly scopes: readonly AccountScope[];
  readonly docs: readonly SyntheticDoc[];
  readonly queries: readonly SyntheticQuery[];
};

export const buildSyntheticCorpus = (): SyntheticCorpus => ({
  scopes: SCOPES,
  docs: [...alphaDocs, ...betaDocs],
  queries: [...alphaQueries, ...betaQueries],
});

export { validateCorpus as validateCorpusRaw } from "./fixtures";
