import { describe, expect, test } from "bun:test";

import {
  createPineconeDeletionCollectionRegistry,
  type PineconeAccountVectorDeleteRequest,
  type PineconeAccountVectorScanRequest,
} from "../../apps/service/workers/pinecone-deletion-cleanup-participant";
import {
  PineconeAccountDeletionClientError,
  createPineconeAccountDeletionVectorClient,
  type PineconeAuthenticatedJsonRequest,
  type PineconeAuthenticatedJsonTransport,
} from "./account-deletion-client";

const registry = createPineconeDeletionCollectionRegistry();
const accountId = "account:pinecone-client";
const scanRequest: PineconeAccountVectorScanRequest = Object.freeze({
  version: "pinecone-account-vector-scan-request-v1",
  role: "memory_vectors",
  namespace: "ns2",
  account_id: accountId,
  limit: 10_000,
  pagination_token: null,
});
const deleteRequest: PineconeAccountVectorDeleteRequest = Object.freeze({
  version: "pinecone-account-vector-delete-request-v1",
  role: "memory_vectors",
  namespace: "ns2",
  account_id: accountId,
});

describe("Pinecone account-deletion data-plane client", () => {
  test("uses the pinned fetch-by-metadata and delete endpoints and returns IDs only", async () => {
    const requests: PineconeAuthenticatedJsonRequest[] = [];
    const transport: PineconeAuthenticatedJsonTransport = {
      async request(request) {
        requests.push(request);
        if (request.path.endsWith("fetch_by_metadata")) {
          return { status: 200, body: {
            namespace: "ns2",
            vectors: { "memproj:abc": { id: "memproj:abc", values: [1, 2], metadata: { uid: accountId, secret: "must-drop" } } },
            pagination: { next: "next-token" },
            usage: { read_units: 1 },
          } };
        }
        return { status: 200, body: { ignored: "provider body is not retained" } };
      },
    };
    const client = createPineconeAccountDeletionVectorClient(registry, transport);
    const page = await client.scanAccountVectors(scanRequest);
    expect(page.vector_ids).toEqual(["memproj:abc"]);
    expect(page.next_pagination_token).toBe("next-token");
    const deletion = await client.deleteAccountVectors(deleteRequest);
    expect(deletion.namespace).toBe("ns2");
    expect(requests.map((request) => `${request.api_version} ${request.method} ${request.path}`)).toEqual([
      "2025-10 POST /vectors/fetch_by_metadata", "2025-10 POST /vectors/delete",
    ]);
    expect(requests[0]?.body).toEqual({
      namespace: "ns2", filter: { uid: { $eq: accountId } }, limit: 10_000,
    });
    expect(requests[1]?.body).toEqual({ namespace: "ns2", filter: { uid: { $eq: accountId } } });
    expect(JSON.stringify(deletion)).not.toContain("secret");
  });

  test("forwards the opaque pagination token only on subsequent pages", async () => {
    let captured: PineconeAuthenticatedJsonRequest | undefined;
    const client = createPineconeAccountDeletionVectorClient(registry, {
      async request(request) {
        captured = request;
        return { status: 200, body: { namespace: "ns2", vectors: {}, pagination: { next: null } } };
      },
    });
    await client.scanAccountVectors(Object.freeze({ ...scanRequest, pagination_token: "opaque" }));
    expect(captured?.body).toEqual({
      namespace: "ns2", filter: { uid: { $eq: accountId } }, limit: 10_000, paginationToken: "opaque",
    });
    expect(captured?.api_version).toBe("2025-10");
  });

  test("rejects invalid coordinates, cross-namespace requests, proxies, and provider failures before/after I/O", async () => {
    let calls = 0;
    const client = createPineconeAccountDeletionVectorClient(registry, {
      async request() {
        calls += 1;
        return { status: 500, body: { secret: "not exposed" } };
      },
    });
    await expect(client.scanAccountVectors(Object.freeze({ ...scanRequest, account_id: "bad id" })))
      .rejects.toMatchObject({ code: "invalid_input" });
    await expect(client.scanAccountVectors(Object.freeze({ ...scanRequest, namespace: "ns1" })))
      .rejects.toMatchObject({ code: "invalid_input" });
    await expect(client.scanAccountVectors(Object.freeze({ ...scanRequest, pagination_token: "bad token\n" })))
      .rejects.toMatchObject({ code: "invalid_input" });
    await expect(client.scanAccountVectors(scanRequest)).rejects.toMatchObject({ code: "provider_failed" });
    expect(calls).toBe(1);
    const proxyTransport = new Proxy({ request: async () => ({ status: 200, body: {} }) }, {});
    expect(() => createPineconeAccountDeletionVectorClient(registry, proxyTransport)).toThrow(
      PineconeAccountDeletionClientError,
    );
  });

  test("rejects a vector map whose key disagrees with its contained id", async () => {
    const client = createPineconeAccountDeletionVectorClient(registry, {
      async request() {
        return { status: 200, body: { namespace: "ns2", vectors: { wrong: { id: "right" } } } };
      },
    });
    await expect(client.scanAccountVectors(scanRequest)).rejects.toMatchObject({ code: "provider_failed" });
  });

  test("deep-freezes the ownership filter before handing it to an untrusted transport", async () => {
    let seenDigest: string | undefined;
    const client = createPineconeAccountDeletionVectorClient(registry, {
      async request(request) {
        expect(() => {
          (request.body.filter as { uid: { $eq: string } }).uid.$eq = "attacker";
        }).toThrow();
        if (request.path === "/vectors/delete") {
          return { status: 200, body: null };
        }
        seenDigest = JSON.stringify(request.body);
        return { status: 200, body: { namespace: "ns2", vectors: {}, pagination: { next: null } } };
      },
    });
    await client.scanAccountVectors(scanRequest);
    expect(seenDigest).toContain(accountId);
  });
});
