import { describe, expect, test } from "bun:test";

import {
  GCS_DELETION_PAGE_SIZE,
  GCS_DELETION_ROLES,
  createGcsDeletionCollectionRegistry,
} from "../../apps/service/workers/gcs-deletion-cleanup-participant";
import {
  GcsAccountDeletionClientError,
  createGcsAccountDeletionObjectClient,
  type GcsAuthenticatedJsonRequest,
} from "./account-deletion-client";

const digest = (letter: string): string => letter.repeat(64);
const registry = createGcsDeletionCollectionRegistry({
  roles: GCS_DELETION_ROLES.map((role, index) => ({
    role,
    bucket_name: `account-${index}-objects`,
    prefix_family: "account_uid_v1" as const,
    policy_digest: digest("a"),
    coverage_digest: digest("b"),
    enumerate_versions: true as const,
    enumerate_soft_deleted: true as const,
  })),
});
const listRequest = Object.freeze({ version: "gcs-account-object-list-request-v1" as const, role: "speech_profiles" as const, bucket_name: "account-0-objects", prefix: "acct/speech/", owner_mapping_digest: digest("e"), mode: "live" as const, page_token: null, limit: GCS_DELETION_PAGE_SIZE });
const deleteRequest = Object.freeze({ version: "gcs-account-object-delete-request-v1" as const, role: "speech_profiles" as const, bucket_name: "account-0-objects", name: "acct/speech_profile.wav", generation: "123", metageneration: "4", owner_mapping_digest: digest("e") });

describe("GCS account-deletion client", () => {
  test("lists all object generations by page and emits metadata-only objects", async () => {
    const seen: GcsAuthenticatedJsonRequest[] = [];
    const client = createGcsAccountDeletionObjectClient(registry, {
      async request(request) {
        seen.push(request);
        return { status: 200, body: { items: [{ name: "acct/speech_profile.wav", generation: "123", metageneration: "4", size: "9", updated: "2026-01-01T00:00:00Z", eventBasedHold: true, secret: "drop" }], nextPageToken: "next" } };
      },
    });
    const page = await client.listAccountObjects(listRequest);
    expect(page.objects[0]).toMatchObject({ name: "acct/speech_profile.wav", generation: "123", retention_held: true });
    expect(JSON.stringify(page)).not.toContain("secret");
    expect(seen[0]).toMatchObject({ api_version: "storage-json-v1", method: "GET", query: { prefix: "acct/speech/", maxResults: "1000" } });
    const continued = await client.listAccountObjects(Object.freeze({ ...listRequest, page_token: "next" }));
    expect(continued.page_token).toBe("next");
    expect(seen[1]?.query.pageToken).toBe("next");
  });

  test("pins versions/softDeleted list modes and exact-generation delete preconditions", async () => {
    const seen: GcsAuthenticatedJsonRequest[] = [];
    const client = createGcsAccountDeletionObjectClient(registry, {
      async request(request) {
        seen.push(request);
        return request.method === "GET"
          ? { status: 200, body: { items: [] } }
          : { status: 204, body: null };
      },
    });
    await client.listAccountObjects(Object.freeze({ ...listRequest, mode: "versions" }));
    await client.listAccountObjects(Object.freeze({ ...listRequest, mode: "soft_deleted" }));
    const result = await client.deleteAccountObject(deleteRequest);
    expect(result.status).toBe("deleted");
    expect(seen[0]?.query.versions).toBe("true");
    expect(seen[1]?.query.softDeleted).toBe("true");
    expect(seen[2]).toMatchObject({ method: "DELETE", query: { generation: "123", ifGenerationMatch: "123", ifMetagenerationMatch: "4" } });
    expect(seen[2]?.path).toContain("acct%2Fspeech_profile.wav");
  });

  test("maps not-found deletes to replay-safe already_absent and rejects hostile input", async () => {
    let calls = 0;
    const client = createGcsAccountDeletionObjectClient(registry, {
      async request() { calls += 1; return { status: 404, body: null }; },
    });
    await expect(client.deleteAccountObject(deleteRequest)).resolves.toMatchObject({ status: "already_absent" });
    await expect(client.listAccountObjects(Object.freeze({ ...listRequest, bucket_name: "foreign" }))).rejects.toMatchObject({ code: "invalid_input" });
    await expect(client.listAccountObjects(Object.freeze({ ...listRequest, page_token: "bad token\n" }))).rejects.toMatchObject({ code: "invalid_input" });
    await expect(client.listAccountObjects(Object.freeze({ ...listRequest, prefix: "x".repeat(1025) }))).rejects.toMatchObject({ code: "invalid_input" });
    const malformed = createGcsAccountDeletionObjectClient(registry, { async request() { return { status: 200, body: { items: [{ name: "a", generation: "1", metageneration: "1", size: "1", updated: "2026-01-01T00:00:00Z", eventBasedHold: "yes" }] } }; } });
    await expect(malformed.listAccountObjects(listRequest)).rejects.toMatchObject({ code: "provider_failed" });
    expect(calls).toBe(1);
    expect(() => createGcsAccountDeletionObjectClient(registry, new Proxy({ request: async () => ({ status: 200, body: {} }) }, {}))).toThrow(GcsAccountDeletionClientError);
  });
});
