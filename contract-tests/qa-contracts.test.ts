import { describe, expect, test } from "bun:test";

import {
  verifyArtifactRecords,
  verifyInstalledContract,
  verifyTarballBytes,
} from "../scripts/qa-contracts.ts";
import type { ContractLock } from "../scripts/qa-contracts.ts";

const root = new URL("../", import.meta.url);

async function readJson<T>(path: string): Promise<T> {
  return await Bun.file(new URL(path, root)).json() as T;
}

describe("contract QA rejects drift", () => {
  test("tampered tarball bytes fail their pinned digest", async () => {
    const lock = await readJson<ContractLock>("contracts.lock.json");
    const bytes = new Uint8Array(await Bun.file(new URL(lock.artifact.path, root)).arrayBuffer());
    const tampered = bytes.slice();
    const lastIndex = tampered.length - 1;
    if (lastIndex < 0) throw new Error("fixture tarball must not be empty");
    tampered[lastIndex] = tampered[lastIndex]! ^ 1;
    expect(() => verifyTarballBytes(tampered, lock.artifact)).toThrow("tarball SHA-256 mismatch");
  });

  test("tampered provenance cannot claim the pinned source digest", async () => {
    const lock = await readJson<ContractLock>("contracts.lock.json");
    const artifact = await readJson<Parameters<typeof verifyArtifactRecords>[1]>(lock.artifact.metadataPath);
    const provenance = await readJson<Parameters<typeof verifyArtifactRecords>[2]>(lock.artifact.provenancePath);
    const tampered = structuredClone(provenance);
    tampered.sourceDigest = "0".repeat(64);
    expect(() => verifyArtifactRecords(lock, artifact, tampered)).toThrow("provenance source digest mismatch");
  });

  test("installed file-list drift is rejected", async () => {
    const lock = await readJson<ContractLock>("contracts.lock.json");
    const manifest = await readJson<Parameters<typeof verifyInstalledContract>[1]>(
      "node_modules/@omi-core/ratified-contracts/package.json",
    );
    const provenance = await readJson<Parameters<typeof verifyInstalledContract>[3]>(
      "node_modules/@omi-core/ratified-contracts/PROVENANCE.json",
    );
    const files = lock.artifact.files.map((path) => path.replace(/^package\//, ""));
    expect(() => verifyInstalledContract(lock, manifest, [...files, "unexpected.json"], provenance)).toThrow(
      "installed file list mismatch",
    );
  });

  test("installed manifest identity and exports cannot drift", async () => {
    const lock = await readJson<ContractLock>("contracts.lock.json");
    const manifest = await readJson<Parameters<typeof verifyInstalledContract>[1]>(
      "node_modules/@omi-core/ratified-contracts/package.json",
    );
    const provenance = await readJson<Parameters<typeof verifyInstalledContract>[3]>(
      "node_modules/@omi-core/ratified-contracts/PROVENANCE.json",
    );
    const files = lock.artifact.files.map((path) => path.replace(/^package\//, ""));
    expect(() => verifyInstalledContract(lock, { ...manifest, version: "0.1.1" }, files, provenance)).toThrow(
      "installed package version mismatch",
    );
    expect(() => verifyInstalledContract(lock, { ...manifest, exports: { ".": "./index.js" } }, files, provenance)).toThrow(
      "installed exports mismatch",
    );
  });
});
