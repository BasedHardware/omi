import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { ADMIN_FINOPS_TABLES } from "../wall-finops";
import { bigQueryFailure, WallSourceError } from "../wall-source-error";

const root = path.resolve(process.cwd());
function sources(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory())
      return entry.name === "__tests__" || entry.name === "node_modules"
        ? []
        : sources(full);
    return /\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)
      ? [full]
      : [];
  });
}

describe("admin omi_finops reads need table-level grants", () => {
  it("lists every omi_finops table the admin source reads", () => {
    const read = new Set<string>();
    for (const file of [
      ...sources(path.join(root, "lib")),
      ...sources(path.join(root, "app")),
    ])
      for (const m of Array.from(
        readFileSync(file, "utf8").matchAll(/omi_finops\.([a-z_0-9]+)/g)
      ))
        read.add(`omi_finops.${m[1]}`);
    // A table added to a query without a grant renders as a blank tile
    // (2026-10-28: five tables, every margin tile). Add it to the list and grant it.
    expect(Array.from(read).sort()).toEqual([...ADMIN_FINOPS_TABLES].sort());
  });
});

describe("bigQueryFailure", () => {
  const tables = [
    "omi_finops.unit_cost_daily",
    "omi_finops.mercury_saas_daily",
  ];
  it("names the ungranted table without forwarding upstream text", () => {
    const error = Object.assign(
      new Error(
        "Access Denied: Table based-hardware:omi_finops.mercury_saas_daily: User does not have permission to query table secret-detail"
      ),
      { code: 403, errors: [{ reason: "accessDenied" }] }
    );
    const failure = bigQueryFailure(error, tables, "fallback");
    expect(failure).toBeInstanceOf(WallSourceError);
    expect(failure.message).toBe(
      "omi_finops.mercury_saas_daily not readable by the admin BigQuery identity (missing dataViewer grant)"
    );
    expect(failure.message).not.toContain("secret-detail");
  });

  it("reports a missing table", () => {
    const error = Object.assign(
      new Error("Not found: Table based-hardware:omi_finops.unit_cost_daily"),
      { code: 404 }
    );
    expect(bigQueryFailure(error, tables, "fallback").message).toBe(
      "omi_finops.unit_cost_daily not found (table not created yet)"
    );
  });

  it("keeps the caller's fallback (and retryability) for anything else", () => {
    const failure = bigQueryFailure(
      new Error("socket hang up"),
      tables,
      "x",
      true
    );
    expect(failure.message).toBe("x");
    expect(failure.retryable).toBe(true);
  });

  it("does not blame a table grant for a project-level denial", () => {
    const failure = bigQueryFailure(
      {
        code: 403,
        message:
          "Access Denied: Project based-hardware: User does not have bigquery.jobs.create permission",
      },
      tables,
      "x",
      true
    );
    expect(failure.message).toBe(
      "FinOps BigQuery permission denied for the admin identity (not table-specific)"
    );
    expect(failure.retryable).toBe(true);
  });
});
