import { describe, expect, test } from "bun:test";

import {
  createTypesenseAccountDeletionDocumentClient,
  TypesenseAccountDeletionClientError,
  type TypesenseAuthenticatedJsonRequest,
  type TypesenseAuthenticatedJsonTransport,
} from "./account-deletion-client";
import { createTypesenseDeletionCollectionRegistry } from
  "../../apps/service/workers/typesense-deletion-cleanup-participant";

const accountId = "account:typesense-cleanup";
const registry = createTypesenseDeletionCollectionRegistry({
  legacy_conversations_collection: "conversations",
  canonical_memory_atoms_collection: "canonical_memory_atoms",
});

const scanRequest = Object.freeze({
  version: "typesense-account-document-scan-request-v1" as const,
  role: "legacy_conversations" as const,
  collection_name: "conversations",
  account_id: accountId,
  page: 2,
  per_page: 250 as const,
});

describe("Typesense account-deletion HTTP client", () => {
  test("uses the exact account filter, ID-only search, and bounded provider pagination", async () => {
    const requests: TypesenseAuthenticatedJsonRequest[] = [];
    const transport: TypesenseAuthenticatedJsonTransport = {
      async request(request) {
        requests.push(request);
        return Object.freeze({
          status: 200,
          body: Object.freeze({
            found: 2,
            hits: Object.freeze([
              Object.freeze({
                document: Object.freeze({ id: "conversation-1", content: "must-not-escape" }),
                highlights: Object.freeze([{ snippet: "must-not-escape" }]),
              }),
              Object.freeze({ document: Object.freeze({ id: "conversation-2" }) }),
            ]),
            search_time_ms: 1,
          }),
        });
      },
    };
    const client = createTypesenseAccountDeletionDocumentClient(registry, transport);
    await expect(client.scanAccountDocuments(scanRequest)).resolves.toEqual({
      version: "typesense-account-document-scan-page-v1",
      role: "legacy_conversations",
      collection_name: "conversations",
      account_id: accountId,
      page: 2,
      found: 2,
      document_ids: ["conversation-1", "conversation-2"],
    });
    expect(requests).toEqual([{
      method: "GET",
      path: "/collections/conversations/documents/search",
      query: {
        q: "*",
        query_by: "structured.overview,structured.title",
        filter_by: "userId:=`account:typesense-cleanup`",
        include_fields: "id",
        highlight_fields: "none",
        page: "2",
        per_page: "250",
        use_cache: "false",
      },
    }]);
    expect(JSON.stringify(await client.scanAccountDocuments(scanRequest)))
      .not.toContain("must-not-escape");
  });

  test("deletes by the same exact account filter and returns a content-free digest receipt", async () => {
    const requests: TypesenseAuthenticatedJsonRequest[] = [];
    const client = createTypesenseAccountDeletionDocumentClient(registry, {
      async request(request) {
        requests.push(request);
        return Object.freeze({ status: 200, body: Object.freeze({ num_deleted: 7 }) });
      },
    });
    const result = await client.deleteAccountDocuments(Object.freeze({
      version: "typesense-account-document-delete-request-v1",
      role: "canonical_memory_atoms",
      collection_name: "canonical_memory_atoms",
      account_id: accountId,
    }));
    expect(result).toMatchObject({
      role: "canonical_memory_atoms",
      account_id: accountId,
      num_deleted: 7,
    });
    expect(result.provider_receipt_digest).toMatch(/^[0-9a-f]{64}$/);
    expect(requests).toEqual([{
      method: "DELETE",
      path: "/collections/canonical_memory_atoms/documents",
      query: {
        filter_by: "userId:=`account:typesense-cleanup`",
        batch_size: "100",
      },
    }]);
  });

  test("rejects provider errors and malformed/accessor responses without exposing detail", async () => {
    const sentinel = "provider-secret-and-document-content";
    const failing = createTypesenseAccountDeletionDocumentClient(registry, {
      async request() { throw new Error(sentinel); },
    });
    await expect(failing.scanAccountDocuments(scanRequest)).rejects
      .toEqual(new TypesenseAccountDeletionClientError("provider_failed"));

    let getterCalls = 0;
    const hostileBody = Object.defineProperty({ hits: [] }, "found", {
      enumerable: true,
      get() { getterCalls += 1; return 0; },
    });
    const hostile = createTypesenseAccountDeletionDocumentClient(registry, {
      async request() { return { status: 200, body: hostileBody }; },
    });
    await expect(hostile.scanAccountDocuments(scanRequest)).rejects
      .toEqual(new TypesenseAccountDeletionClientError("provider_failed"));
    expect(getterCalls).toBe(0);

    const denied = createTypesenseAccountDeletionDocumentClient(registry, {
      async request() { return { status: 401, body: { message: sentinel } }; },
    });
    await expect(denied.scanAccountDocuments(scanRequest)).rejects
      .toEqual(new TypesenseAccountDeletionClientError("provider_failed"));
  });

  test("rejects invalid coordinates before transport and captures the transport method", async () => {
    let calls = 0;
    const transport: TypesenseAuthenticatedJsonTransport = {
      async request() {
        calls += 1;
        return { status: 200, body: { found: 0, hits: [] } };
      },
    };
    const client = createTypesenseAccountDeletionDocumentClient(registry, transport);
    transport.request = async () => { throw new Error("mutated method"); };
    await expect(client.scanAccountDocuments(scanRequest)).resolves.toMatchObject({ found: 0 });
    expect(calls).toBe(1);

    await expect(client.scanAccountDocuments({
      ...scanRequest,
      account_id: "bad account filter && userId:=other",
    })).rejects.toEqual(new TypesenseAccountDeletionClientError("invalid_input"));
    await expect(client.scanAccountDocuments({
      ...scanRequest,
      page: 402,
    })).rejects.toEqual(new TypesenseAccountDeletionClientError("invalid_input"));
    await expect(client.scanAccountDocuments({
      ...scanRequest,
      role: "canonical_memory_atoms",
    })).rejects.toEqual(new TypesenseAccountDeletionClientError("invalid_input"));
    expect(calls).toBe(1);
  });
});
