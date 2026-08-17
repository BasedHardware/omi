import { afterEach, describe, expect, test } from "bun:test";
import { mkdtempSync, mkdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  ClosureVerificationError,
  verifyProductionDependencyClosure,
} from "./verify-production-dependency-closure.mjs";

const roots = [];

afterEach(() => {
  while (roots.length > 0) rmSync(roots.pop(), { recursive: true, force: true });
});

function root() {
  const path = mkdtempSync(join(tmpdir(), "omi-production-closure-test-"));
  roots.push(path);
  for (const directory of ["apps", "core", "drivers", "node_modules"]) {
    mkdirSync(join(path, directory), { recursive: true });
  }
  writeFileSync(
    join(path, "apps", "service.ts"),
    'import { initializeApp } from "firebase-admin/app";\nimport { getAuth } from "firebase-admin/auth";\n',
  );
  return path;
}

function pkg(rootPath, relativePath, name, version, manifest) {
  const directory = join(rootPath, "node_modules", relativePath);
  mkdirSync(directory, { recursive: true });
  writeFileSync(
    join(directory, "package.json"),
    manifest ?? JSON.stringify({ name, version }),
  );
  return directory;
}

function validHoisted() {
  const path = root();
  pkg(path, "firebase-admin", "firebase-admin", "14.2.0");
  pkg(path, "hono", "hono", "4.12.34");
  pkg(path, "google-auth-library", "google-auth-library", "10.9.1");
  pkg(path, "gaxios", "gaxios", "7.3.0");
  return path;
}

function code(error) {
  expect(error).toBeInstanceOf(ClosureVerificationError);
  return error.code;
}

describe("production dependency closure", () => {
  test("accepts an omitted-optional hoisted closure", () => {
    expect(verifyProductionDependencyClosure(validHoisted())).toEqual({
      status: "ok",
      package_count: 4,
      required: { "firebase-admin": "14.2.0", hono: "4.12.34" },
    });
  });

  test("accepts an isolated in-root store and deduplicates its links", () => {
    const path = root();
    for (const [entry, name, version] of [
      ["firebase-admin@14.2.0", "firebase-admin", "14.2.0"],
      ["hono@4.12.34", "hono", "4.12.34"],
    ]) {
      const directory = join(path, "node_modules", ".bun", entry, "node_modules", name);
      mkdirSync(directory, { recursive: true });
      writeFileSync(join(directory, "package.json"), JSON.stringify({ name, version }));
      symlinkSync(join(".bun", entry, "node_modules", name), join(path, "node_modules", name));
    }
    expect(verifyProductionDependencyClosure(path).package_count).toBe(2);
  });

  test.each([
    ["uuid", "uuid", "9.0.1"],
    ["@google-cloud/storage", "@google-cloud/storage", "7.22.0"],
    ["@google-cloud/firestore", "@google-cloud/firestore", "8.7.1"],
  ])("rejects forbidden installed package %s", (relativePath, name, version) => {
    const path = validHoisted();
    pkg(path, relativePath, name, version);
    expect(() => verifyProductionDependencyClosure(path)).toThrow("forbidden_package_installed");
  });

  test("rejects a forbidden package nested below an allowed package", () => {
    const path = validHoisted();
    pkg(path, "gaxios/node_modules/uuid", "uuid", "9.0.1");
    expect(() => verifyProductionDependencyClosure(path)).toThrow(
      "forbidden_package_installed",
    );
  });

  test.each([
    ["gaxios", "gaxios", "6.7.1", "legacy_optional_gaxios_installed"],
    [
      "google-auth-library",
      "google-auth-library",
      "9.15.1",
      "legacy_optional_google_auth_installed",
    ],
  ])("rejects legacy optional-path package %s", (relativePath, name, version, expected) => {
    const path = validHoisted();
    const target = join(path, "node_modules", relativePath, "package.json");
    writeFileSync(target, JSON.stringify({ name, version }));
    expect(() => verifyProductionDependencyClosure(path)).toThrow(expected);
  });

  test("rejects a missing required package", () => {
    const path = root();
    pkg(path, "hono", "hono", "4.12.34");
    expect(() => verifyProductionDependencyClosure(path)).toThrow("required_package_missing");
  });

  test("rejects a duplicate required package by canonical directory", () => {
    const path = validHoisted();
    pkg(path, "holder", "holder", "1.0.0");
    pkg(
      path,
      "holder/node_modules/firebase-admin",
      "firebase-admin",
      "14.2.0",
    );
    expect(() => verifyProductionDependencyClosure(path)).toThrow("required_package_duplicated");
  });

  test("rejects required version drift", () => {
    const path = validHoisted();
    writeFileSync(
      join(path, "node_modules", "hono", "package.json"),
      JSON.stringify({ name: "hono", version: "4.13.1" }),
    );
    expect(() => verifyProductionDependencyClosure(path)).toThrow(
      "required_package_version_mismatch",
    );
  });

  test("rejects malformed package manifests", () => {
    const path = validHoisted();
    pkg(path, "extra", "extra", "1.0.0", "{");
    expect(() => verifyProductionDependencyClosure(path)).toThrow("package_manifest_malformed");
  });

  test("rejects package links outside the artifact root", () => {
    const path = validHoisted();
    const external = mkdtempSync(join(tmpdir(), "omi-production-closure-external-"));
    roots.push(external);
    writeFileSync(join(external, "package.json"), JSON.stringify({ name: "extra", version: "1.0.0" }));
    symlinkSync(external, join(path, "node_modules", "extra"));
    expect(() => verifyProductionDependencyClosure(path)).toThrow("package_link_outside_root");
  });

  test("rejects an unresolvable package link", () => {
    const path = validHoisted();
    symlinkSync("missing-target", join(path, "node_modules", "extra"));
    expect(() => verifyProductionDependencyClosure(path)).toThrow("package_link_unresolvable");
  });

  test("rejects an external nested dependency root", () => {
    const path = validHoisted();
    const external = mkdtempSync(join(tmpdir(), "omi-production-closure-modules-"));
    roots.push(external);
    symlinkSync(external, join(path, "node_modules", "gaxios", "node_modules"));
    expect(() => verifyProductionDependencyClosure(path)).toThrow(
      "package_link_outside_root",
    );
  });

  test("rejects forbidden production imports but ignores tests", () => {
    const path = validHoisted();
    writeFileSync(
      join(path, "apps", "service.test.ts"),
      'import { getStorage } from "firebase-admin/storage";\n',
    );
    expect(verifyProductionDependencyClosure(path).status).toBe("ok");
    writeFileSync(
      join(path, "drivers", "storage.ts"),
      'import { getStorage } from "firebase-admin/storage";\n',
    );
    try {
      verifyProductionDependencyClosure(path);
      throw new Error("expected rejection");
    } catch (error) {
      expect(code(error)).toBe("forbidden_optional_import");
    }
  });
});
