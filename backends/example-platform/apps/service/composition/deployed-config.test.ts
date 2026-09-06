import { expect, test } from "bun:test";
import { readDeployedConfig } from "./deployed-config";
import { createProductionCursor } from "./production-cursor";
import type { ApplicationReadSnapshotAttestation } from "../../../core/retrieve/application-read";

const env = {
  OMI_TRANSCRIPTION_API_KEY: "test-only", OMI_TRANSCRIPTION_MODEL: "nova-3",
  OMI_ACCOUNT_TIMEZONE: "UTC",
  OMI_DATABASE_URL: "postgres://app:test-only@localhost/db",
  OMI_FIREBASE_PROJECT_ID: "test-project", OMI_APPLICATION_ID: "app:test",
  OMI_DATABASE_GENERATION_DIGEST: "a".repeat(64), OMI_CODEC_KEY_HEX: "b".repeat(64), OMI_CURSOR_KEY_HEX: "c".repeat(64),
  OMI_LLM_GATEWAY_URL: "https://gateway.example", OMI_LLM_GATEWAY_SERVICE_TOKEN: "test-only", OMI_MEMORY_RENDER_LANE: "omi:auto:memory-render",
};
test("deployed configuration has stable keys and never admits missing credentials or emulator auth", () => {
  expect(readDeployedConfig(env).gatewayEndpoint).toBe("https://gateway.example/v1/chat/completions");
  expect(readDeployedConfig(env).codecKey).toEqual(readDeployedConfig(env).codecKey);
  for (const key of Object.keys(env)) expect(() => readDeployedConfig({ ...env, [key]: undefined })).toThrow();
  expect(() => readDeployedConfig({ ...env, FIREBASE_AUTH_EMULATOR_HOST: "localhost:9099" })).toThrow();
  expect(() => readDeployedConfig({ ...env, PORT: "0" })).toThrow();
});

test("production cursor survives process restart but rejects each changed authorization or projection coordinate", () => {
  const keys = { active_key_id: "v1", keys: [{ key_id: "v1", secret: new Uint8Array(32).fill(1) }] };
  const fields = ["owner_identity_digest", "application_identity_digest", "credential_identity_digest", "authorization_state_digest", "grant_state_digest", "account_head_digest", "authorized_graph_digest", "coherent_projection_commit_digest", "visibility_digest", "filter_digest", "query_digest", "source_digest", "read_mode_digest", "synthesized_projection_generation_digest", "projected_content_digest", "durable_generation_digest", "overlay_generation_digest", "declared_generation_digest", "accepted_generation_digest", "stm_generation_digest"];
  const attestation = { ...Object.fromEntries(fields.map(key => [key, "a".repeat(64)])), read_timestamp_epoch_seconds: 1800000000, coverage: { declared_frontier: "frontier", accepted: { state: "unavailable", searched_frontier: null }, stm: { state: "unavailable", searched_frontier: null }, projection_freshness: "fresh", intentional_bounds: [] } } as unknown as ApplicationReadSnapshotAttestation;
  const key = `vk1_${"b".repeat(64)}`;
  const cursor = createProductionCursor(keys).issueCursor(key, attestation);
  const restarted = createProductionCursor(keys);
  expect(restarted.verifyCursor(cursor, { ...attestation, read_timestamp_epoch_seconds: 1800000001 })).toBe(key);
  for (const field of fields) expect(() => restarted.verifyCursor(cursor, { ...attestation, [field]: "c".repeat(64) })).toThrow();
  expect(() => restarted.verifyCursor(cursor, { ...attestation, read_timestamp_epoch_seconds: 1800000901 })).toThrow();
  expect(() => restarted.verifyCursor(cursor, { ...attestation, coverage: { ...attestation.coverage, projection_freshness: "stale" } })).toThrow();
});

test("optional socket directory is explicit and rejects ambiguous paths", () => {
  expect(readDeployedConfig(env).databaseSocketDirectory).toBeUndefined();
  expect(readDeployedConfig({...env, OMI_DATABASE_SOCKET_DIRECTORY: "/cloudsql/dev:region:database"}).databaseSocketDirectory).toBe("/cloudsql/dev:region:database");
  for (const value of ["", "localhost", "/tmp/../database", "/tmp/", "/tmp\u0000/socket"])
    expect(() => readDeployedConfig({...env, OMI_DATABASE_SOCKET_DIRECTORY: value})).toThrow("invalid_database_socket_directory");
});
