import type { RawDoc, RawQuery, ValidationResult } from "./types";

const SYNTHETIC_ACCOUNT = /^acct-synthetic-[a-z]+$/;

const PROD_LIKE_FIELDS: ReadonlySet<string> = new Set([
  "email",
  "phone",
  "token",
  "secret",
  "apikey",
  "password",
  "userid",
  "messagetext",
  "transcript",
  "conversation",
  "sessiontoken",
  "accesstoken",
  "refreshtoken",
  "ssn",
  "address",
  "creditcard",
  "credential",
  "jwt",
  "cookie",
]);

const isFiniteNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);

const isNonEmptyString = (value: unknown): value is string =>
  typeof value === "string" && value.length > 0;

const isStringArray = (value: unknown): value is readonly string[] =>
  Array.isArray(value) && value.every(isNonEmptyString);

const isNumberArray = (value: unknown): value is readonly number[] =>
  Array.isArray(value) && value.length > 0 && value.every(isFiniteNumber);

const prodLikeFields = (record: RawDoc | RawQuery): string[] => {
  const hits: string[] = [];
  for (const key of Object.keys(record)) {
    if (PROD_LIKE_FIELDS.has(key.toLowerCase())) hits.push(key);
  }
  return hits;
};

const validateDocShape = (doc: RawDoc, index: number): string[] => {
  const reasons: string[] = [];
  if (doc["synthetic"] !== true) {
    reasons.push(`doc[${index}] synthetic flag must be literally true`);
  }
  const account = doc["accountId"];
  if (typeof account !== "string" || !SYNTHETIC_ACCOUNT.test(account)) {
    reasons.push(
      `doc[${index}] accountId must match synthetic scope pattern acct-synthetic-*`
    );
  }
  if (!isNonEmptyString(doc["id"])) {
    reasons.push(`doc[${index}] id must be a non-empty string`);
  }
  if (!isNumberArray(doc["embedding"])) {
    reasons.push(`doc[${index}] embedding must be a non-empty finite number[]`);
  }
  if (!isStringArray(doc["terms"])) {
    reasons.push(`doc[${index}] terms must be a non-empty string[]`);
  }
  if (typeof doc["revoked"] !== "boolean") {
    reasons.push(`doc[${index}] revoked must be boolean`);
  }
  const prod = prodLikeFields(doc);
  if (prod.length > 0) {
    reasons.push(
      `doc[${index}] carries production-like field(s): ${prod.join(", ")}`
    );
  }
  return reasons;
};

const validateQueryShape = (query: RawQuery, index: number): string[] => {
  const reasons: string[] = [];
  const account = query["accountId"];
  if (typeof account !== "string" || !SYNTHETIC_ACCOUNT.test(account)) {
    reasons.push(
      `query[${index}] accountId must match synthetic scope pattern acct-synthetic-*`
    );
  }
  if (!isNonEmptyString(query["id"])) {
    reasons.push(`query[${index}] id must be a non-empty string`);
  }
  if (!isNumberArray(query["embedding"])) {
    reasons.push(
      `query[${index}] embedding must be a non-empty finite number[]`
    );
  }
  if (!isStringArray(query["terms"])) {
    reasons.push(`query[${index}] terms must be a non-empty string[]`);
  }
  if (!Array.isArray(query["relevantDocIds"])) {
    reasons.push(`query[${index}] relevantDocIds must be an array`);
  }
  const prod = prodLikeFields(query);
  if (prod.length > 0) {
    reasons.push(
      `query[${index}] carries production-like field(s): ${prod.join(", ")}`
    );
  }
  return reasons;
};

export const validateCorpus = (
  docs: readonly RawDoc[],
  queries: readonly RawQuery[]
): ValidationResult => {
  const reasons: string[] = [];
  const docIds = new Set<string>();
  const docByAccount = new Map<string, Set<string>>();

  docs.forEach((doc, index) => {
    reasons.push(...validateDocShape(doc, index));
    const id = doc["id"];
    const account = doc["accountId"];
    if (typeof id === "string") {
      if (docIds.has(id)) reasons.push(`doc id ${id} is duplicated`);
      docIds.add(id);
    }
    if (typeof account === "string") {
      let bucket = docByAccount.get(account);
      if (bucket === undefined) {
        bucket = new Set<string>();
        docByAccount.set(account, bucket);
      }
      if (typeof id === "string") bucket.add(id);
    }
  });

  queries.forEach((query, index) => {
    reasons.push(...validateQueryShape(query, index));
    const account = query["accountId"];
    const relevant = query["relevantDocIds"];
    if (!Array.isArray(relevant)) return;
    const sameAccountDocs = docByAccount.get(
      typeof account === "string" ? account : ""
    );
    relevant.forEach((rid) => {
      if (typeof rid !== "string" || !docIds.has(rid)) {
        reasons.push(
          `query[${index}] has unresolved relevance id: ${String(rid)}`
        );
        return;
      }
      if (sameAccountDocs === undefined || !sameAccountDocs.has(rid)) {
        reasons.push(
          `query[${index}] relevance id ${rid} resolves to a foreign account`
        );
      }
    });
  });

  if (reasons.length > 0) return { ok: false, reasons };
  return { ok: true };
};
