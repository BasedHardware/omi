import { describe, expect, test } from "bun:test";

import {
  FIRESTORE_LEGACY_GENERATION_MAX_DOCUMENTS_PER_ACCOUNT,
  createFirestoreLegacyGenerationCollectionRegistry,
} from "../../apps/service/workers/firestore-legacy-generation-cleanup-participant";
import {
  FirestoreLegacyGenerationClientError,
  createFirestoreLegacyGenerationDocumentClient,
  type FirestoreAuthenticatedJsonRequest,
  type FirestoreAuthenticatedJsonTransport,
} from "./legacy-generation-deletion-client";

const digest = (character: string): string => character.repeat(64);
const registry = createFirestoreLegacyGenerationCollectionRegistry({
  project_id: "based-hardware",
  database_id: "(default)",
  policy_digest: digest("a"),
});
const scanRequest = Object.freeze({
  version: "firestore-legacy-generation-scan-request-v1" as const,
  project_id: "based-hardware",
  database_id: "(default)",
  role: "legacy_user_tree" as const,
  collection_id: "users",
  legacy_owner_key: "firebase-uid",
  owner_mapping_digest: digest("b"),
  maximum_documents: FIRESTORE_LEGACY_GENERATION_MAX_DOCUMENTS_PER_ACCOUNT,
});
const fullName = (relative: string): string =>
  `projects/based-hardware/databases/(default)/documents/${relative}`;

describe("Firestore legacy-generation REST client", () => {
  test("recurses missing parents, returns metadata only, and deletes with update-time CAS", async () => {
    const requests: FirestoreAuthenticatedJsonRequest[] = [];
    const transport: FirestoreAuthenticatedJsonTransport = {
      async request(request) {
        requests.push(request);
        if (request.method === "GET" && request.path.endsWith("/users/firebase-uid")) {
          return { status: 200, body: {
            name: fullName("users/firebase-uid"), updateTime: "2026-08-13T11:59:00Z",
          } };
        }
        if (request.method === "POST" && request.path.endsWith("/users/firebase-uid:listCollectionIds")) {
          return { status: 200, body: { collectionIds: ["memories"] } };
        }
        if (request.method === "GET" && request.path.endsWith("/users/firebase-uid/memories")) {
          return { status: 200, body: { documents: [
            { name: fullName("users/firebase-uid/memories/live"), updateTime: "2026-08-13T12:00:00Z" },
            { name: fullName("users/firebase-uid/memories/missing-parent") },
          ] } };
        }
        if (request.method === "POST" && request.path.endsWith("/memories/live:listCollectionIds")) {
          return { status: 200, body: {} };
        }
        if (request.method === "POST" && request.path.endsWith("/memories/missing-parent:listCollectionIds")) {
          return { status: 200, body: { collectionIds: ["children"] } };
        }
        if (request.method === "GET" && request.path.endsWith("/missing-parent/children")) {
          return { status: 200, body: { documents: [
            { name: fullName("users/firebase-uid/memories/missing-parent/children/child"), updateTime: "2026-08-13T12:01:00Z" },
          ] } };
        }
        if (request.method === "POST" && request.path.endsWith("/children/child:listCollectionIds")) {
          return { status: 200, body: {} };
        }
        if (request.method === "DELETE") return { status: 200, body: {} };
        throw new Error(`unexpected request ${request.method} ${request.path}`);
      },
    };
    const client = createFirestoreLegacyGenerationDocumentClient(registry, transport);
    const result = await client.scanCollectionTree(scanRequest);
    expect(result.documents.map((item) => item.document_path)).toEqual([
      "users/firebase-uid",
      "users/firebase-uid/memories/live",
      "users/firebase-uid/memories/missing-parent/children/child",
    ]);
    expect(requests.filter((item) => item.method === "GET").every((item) =>
      item.query["mask.fieldPaths"] === "omi_cleanup_coordinate_only_v1")).toBe(true);
    const child = result.documents.find((item) => item.document_path.endsWith("/children/child"))!;
    const deletion = await client.deleteDocument(Object.freeze({
      version: "firestore-legacy-generation-delete-request-v1",
      project_id: "based-hardware",
      database_id: "(default)",
      role: "legacy_user_tree",
      collection_id: "users",
      legacy_owner_key: "firebase-uid",
      owner_mapping_digest: digest("b"),
      document_path: child.document_path,
      update_time: child.update_time,
    }));
    expect(deletion.result).toBe("deleted");
    expect(requests.at(-1)?.query).toEqual({
      "currentDocument.updateTime": "2026-08-13T12:01:00Z",
    });
  });

  test("rejects pagination cycles and wrong collection coordinates closed", async () => {
    const transport: FirestoreAuthenticatedJsonTransport = {
      async request(request) {
        if (request.method === "GET") {
          return { status: 200, body: { nextPageToken: "same" } };
        }
        return { status: 200, body: {} };
      },
    };
    const client = createFirestoreLegacyGenerationDocumentClient(registry, transport);
    await expect(client.scanCollectionTree(scanRequest)).rejects.toBeInstanceOf(
      FirestoreLegacyGenerationClientError,
    );
    await expect(client.scanCollectionTree(Object.freeze({
      ...scanRequest,
      collection_id: "other",
    }))).rejects.toMatchObject({ code: "invalid_input" });
  });

  test("discovers descendants when the user root document is already absent", async () => {
    const transport: FirestoreAuthenticatedJsonTransport = {
      async request(request) {
        if (request.method === "GET" && request.path.endsWith("/users/firebase-uid")) {
          return { status: 404, body: {} };
        }
        if (request.method === "POST" && request.path.endsWith("/users/firebase-uid:listCollectionIds")) {
          return { status: 200, body: { collectionIds: ["memories"] } };
        }
        if (request.method === "GET" && request.path.endsWith("/users/firebase-uid/memories")) {
          return { status: 200, body: { documents: [
            { name: fullName("users/firebase-uid/memories/survivor"), updateTime: "2026-08-13T12:00:00Z" },
          ] } };
        }
        if (request.method === "POST" && request.path.endsWith("/memories/survivor:listCollectionIds")) {
          return { status: 200, body: {} };
        }
        throw new Error(`unexpected request ${request.method} ${request.path}`);
      },
    };
    const result = await createFirestoreLegacyGenerationDocumentClient(registry, transport)
      .scanCollectionTree(scanRequest);
    expect(result.documents).toEqual([{
      document_path: "users/firebase-uid/memories/survivor",
      update_time: "2026-08-13T12:00:00Z",
    }]);
    expect(result.descendant_complete).toBe(true);
  });

  test("rejects any returned document content instead of hydrating it", async () => {
    const client = createFirestoreLegacyGenerationDocumentClient(registry, {
      async request(request) {
        if (request.method === "GET" && request.path.endsWith("/users/firebase-uid")) {
          return { status: 200, body: {
            name: fullName("users/firebase-uid"),
            updateTime: "2026-08-13T11:59:00Z",
            fields: { private_memory: { stringValue: "must-not-be-read" } },
          } };
        }
        throw new Error("unexpected provider access");
      },
    });
    await expect(client.scanCollectionTree(scanRequest)).rejects.toMatchObject({
      code: "provider_failed",
      message: "provider_failed",
    });
  });

  test("maps not-found deletes to exact replay absence and sanitizes transport errors", async () => {
    const missing = createFirestoreLegacyGenerationDocumentClient(registry, {
      async request() { return { status: 404, body: {} }; },
    });
    const request = Object.freeze({
      version: "firestore-legacy-generation-delete-request-v1" as const,
      project_id: "based-hardware",
      database_id: "(default)",
      role: "legacy_user_tree" as const,
      collection_id: "users",
      legacy_owner_key: "firebase-uid",
      owner_mapping_digest: digest("b"),
      document_path: "users/firebase-uid/memories/missing",
      update_time: "2026-08-13T12:00:00Z",
    });
    expect((await missing.deleteDocument(request)).result).toBe("already_absent");
    const broken = createFirestoreLegacyGenerationDocumentClient(registry, {
      async request() { throw new Error("secret provider response"); },
    });
    await expect(broken.deleteDocument(request)).rejects.toMatchObject({
      code: "provider_failed",
      message: "provider_failed",
    });
  });

  test("rejects hostile owner coordinates without coercion or provider access", async () => {
    let coercions = 0;
    let providerCalls = 0;
    const client = createFirestoreLegacyGenerationDocumentClient(registry, {
      async request() { providerCalls += 1; return { status: 200, body: {} }; },
    });
    const hostileOwner = Object.freeze({
      toString() { coercions += 1; return "firebase-uid"; },
    });
    await expect(client.deleteDocument(Object.freeze({
      version: "firestore-legacy-generation-delete-request-v1",
      project_id: "based-hardware",
      database_id: "(default)",
      role: "legacy_user_tree",
      collection_id: "users",
      legacy_owner_key: hostileOwner,
      owner_mapping_digest: digest("b"),
      document_path: "users/firebase-uid",
      update_time: "2026-08-13T12:00:00Z",
    }) as never)).rejects.toMatchObject({ code: "invalid_input" });
    expect(coercions).toBe(0);
    expect(providerCalls).toBe(0);
  });
});
