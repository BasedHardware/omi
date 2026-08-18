import { D1_MIGRATIONS } from "../migrations/manifest";

export interface D1MigrationEvidenceItem {
  readonly name: string;
  readonly sha256: string;
}

export interface D1MigrationEvidence {
  readonly schema_version: string;
  readonly migrations: readonly D1MigrationEvidenceItem[];
  readonly evidence_id: string;
}

export type MigrationPreflightResult =
  | { kind: "ok"; schemaVersion: string; evidenceId: string }
  | { kind: "error"; reason: string };

export type MigrationPreflightInput = {
  evidenceUrl: string;
  evidenceId: string;
};

export type MigrationPreflightParseResult =
  | { kind: "ok"; value: MigrationPreflightInput }
  | { kind: "error"; reason: string };

const evidenceIdPattern = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const migrationNamePattern = /^[0-9]{4}_[a-z][a-z0-9_-]{0,62}\.sql$/;
const schemaVersionPattern = /^[0-9]{4}_[a-z][a-z0-9_-]{0,62}\.sql$/;
const sha256Pattern = /^[0-9a-f]{64}$/;
const allowedTopKeys = new Set(["schema_version", "migrations", "evidence_id"]);
const allowedItemKeys = new Set(["name", "sha256"]);

export function sanitizeDisplayUrl(input: string): string {
  try {
    new URL(input);
    return "[endpoint]";
  } catch {
    return "[invalid]";
  }
}

export function parseMigrationPreflightArgs(
  args: string[]
): MigrationPreflightParseResult {
  const evidenceUrl = args[0];
  if (evidenceUrl === undefined || evidenceUrl.length === 0) {
    return { kind: "error", reason: "evidence_url_required" };
  }
  const options = new Map<string, string>();
  for (let index = 1; index < args.length; index += 2) {
    const option = args[index];
    const value = args[index + 1];
    if (option === undefined || value === undefined) {
      return { kind: "error", reason: "option_value_required" };
    }
    if (option !== "--evidence") {
      return { kind: "error", reason: "unknown_option" };
    }
    if (options.has(option)) {
      return { kind: "error", reason: "duplicate_option" };
    }
    options.set(option, value);
  }
  const evidenceId = options.get("--evidence");
  if (evidenceId === undefined) {
    return { kind: "error", reason: "evidence_id_required" };
  }
  if (!evidenceIdPattern.test(evidenceId)) {
    return { kind: "error", reason: "invalid_evidence_id" };
  }
  return { kind: "ok", value: { evidenceUrl, evidenceId } };
}

export function verifyMigrationEvidence(
  body: unknown,
  expectedEvidenceId: string
): MigrationPreflightResult {
  if (body === null || typeof body !== "object" || Array.isArray(body)) {
    return { kind: "error", reason: "evidence_not_an_object" };
  }
  const record = body as Record<string, unknown>;
  const extraKeys = Object.keys(record).filter(
    (key) => !allowedTopKeys.has(key)
  );
  if (extraKeys.length > 0) {
    return { kind: "error", reason: "evidence_has_extra_fields" };
  }
  const schemaVersion = record["schema_version"];
  const migrations = record["migrations"];
  const evidenceId = record["evidence_id"];
  if (
    typeof schemaVersion !== "string" ||
    !schemaVersionPattern.test(schemaVersion)
  ) {
    return { kind: "error", reason: "invalid_schema_version" };
  }
  if (!Array.isArray(migrations)) {
    return { kind: "error", reason: "migrations_not_an_array" };
  }
  if (typeof evidenceId !== "string" || !evidenceIdPattern.test(evidenceId)) {
    return { kind: "error", reason: "invalid_evidence_id" };
  }
  if (evidenceId !== expectedEvidenceId) {
    return { kind: "error", reason: "evidence_id_mismatch" };
  }

  const evidenceItems: D1MigrationEvidenceItem[] = [];
  for (const item of migrations) {
    if (item === null || typeof item !== "object" || Array.isArray(item)) {
      return { kind: "error", reason: "migration_item_not_an_object" };
    }
    const recordItem = item as Record<string, unknown>;
    const extraItemKeys = Object.keys(recordItem).filter(
      (key) => !allowedItemKeys.has(key)
    );
    if (extraItemKeys.length > 0) {
      return { kind: "error", reason: "migration_item_has_extra_fields" };
    }
    const name = recordItem["name"];
    const sha256 = recordItem["sha256"];
    if (typeof name !== "string" || !migrationNamePattern.test(name)) {
      return { kind: "error", reason: "invalid_migration_name" };
    }
    if (typeof sha256 !== "string" || !sha256Pattern.test(sha256)) {
      return { kind: "error", reason: "invalid_migration_sha256" };
    }
    evidenceItems.push({ name, sha256 });
  }

  const expectedMigrations = [...D1_MIGRATIONS].sort(
    (a, b) => a.version - b.version
  );
  if (evidenceItems.length !== expectedMigrations.length) {
    return { kind: "error", reason: "migration_count_mismatch" };
  }

  const evidenceByName = new Map(
    evidenceItems.map((item) => [item.name, item])
  );
  if (evidenceByName.size !== evidenceItems.length) {
    return { kind: "error", reason: "duplicate_migration_name" };
  }

  for (const expected of expectedMigrations) {
    const item = evidenceByName.get(expected.name);
    if (item === undefined) {
      return { kind: "error", reason: `migration_missing:${expected.name}` };
    }
    if (item.sha256 !== expected.sha256) {
      return {
        kind: "error",
        reason: `migration_checksum_mismatch:${expected.name}`,
      };
    }
  }

  const latest = expectedMigrations.at(-1);
  if (latest === undefined) {
    return { kind: "error", reason: "migration_manifest_empty" };
  }
  if (schemaVersion !== latest.name) {
    return { kind: "error", reason: "schema_version_mismatch" };
  }

  return { kind: "ok", schemaVersion, evidenceId };
}

export async function verifyMigrations(
  evidenceUrl: string,
  expectedEvidenceId: string
): Promise<MigrationPreflightResult> {
  let response: Response;
  try {
    response = await fetch(evidenceUrl, {
      headers: { accept: "application/json" },
      redirect: "manual",
    });
  } catch {
    return { kind: "error", reason: "fetch_failed" };
  }

  if (response.status !== 200) {
    return { kind: "error", reason: `unexpected status ${response.status}` };
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return { kind: "error", reason: "content-type is not application/json" };
  }

  const cacheControl = response.headers.get("cache-control") ?? "";
  if (!cacheControl.includes("no-store")) {
    return { kind: "error", reason: "cache-control is missing no-store" };
  }

  let body: unknown;
  try {
    body = (await response.json()) as unknown;
  } catch {
    return { kind: "error", reason: "json_parse_failed" };
  }

  return verifyMigrationEvidence(body, expectedEvidenceId);
}

export async function main(args: string[]): Promise<number> {
  const parsed = parseMigrationPreflightArgs(args);
  if (parsed.kind === "error") {
    console.error(`migration preflight failed: ${parsed.reason}`);
    return 1;
  }

  const result = await verifyMigrations(
    parsed.value.evidenceUrl,
    parsed.value.evidenceId
  );
  if (result.kind === "ok") {
    console.log(
      `migration preflight passed: schema_version=${result.schemaVersion}`
    );
    return 0;
  }

  console.error(
    `migration preflight failed: ${result.reason} at ${sanitizeDisplayUrl(
      parsed.value.evidenceUrl
    )}`
  );
  return 1;
}

if (import.meta.main) {
  main(Bun.argv.slice(2))
    .then((code) => process.exit(code))
    .catch(() => process.exit(1));
}
