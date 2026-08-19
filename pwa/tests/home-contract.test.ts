import { expect, test } from "bun:test";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import {
  createSameOriginReadTransport,
  DEMO_CURRENTS,
  filterCurrents,
  loadBackendCurrents,
  type BrowserCurrent,
} from "../src/data";
import {
  createBrowserCapabilityAdapter,
  type BrowserEnvironment,
} from "../src/browser-adapters";

const root = resolve(import.meta.dir, "..");

test("search stays empty until the user enters a query", () => {
  expect(filterCurrents(DEMO_CURRENTS, "")).toEqual([]);
  expect(filterCurrents(DEMO_CURRENTS, "   ")).toEqual([]);
  expect(filterCurrents(DEMO_CURRENTS, "morning")).toHaveLength(1);
});

test("search results retain the existing projection contract fields", () => {
  const result = filterCurrents(DEMO_CURRENTS, "memory")[0] as BrowserCurrent;
  expect(result).toEqual(
    expect.objectContaining({
      kind: "memory",
      id: expect.any(String),
      title: expect.any(String),
      summary: expect.any(String),
      updatedAt: expect.any(Number),
    })
  );
});

test("browser capability adapter never invents a pendant or permission", async () => {
  const environment: BrowserEnvironment = {
    bluetooth: undefined,
    mediaDevices: undefined,
    permissions: undefined,
  };
  const adapter = createBrowserCapabilityAdapter(environment);

  expect(adapter.snapshot()).toEqual({
    bluetooth: "unsupported",
    bluetoothDeviceName: null,
    microphone: "unsupported",
    omiCapture: "unsupported",
  });
  expect(await adapter.chooseBluetoothDevice()).toEqual({
    ok: false,
    reason: "unsupported",
  });
  expect(await adapter.checkMicrophone()).toEqual({
    ok: false,
    reason: "unsupported",
  });
});

test("backend adapter keeps auth out of browser requests and rejects absolute paths", async () => {
  const calls: Array<{
    path: string;
    credentials: RequestCredentials;
    authorization: string | null;
  }> = [];
  const transport = createSameOriginReadTransport(async (input, init) => {
    const headers = new Headers(init?.headers);
    calls.push({
      authorization: headers.get("authorization"),
      credentials: init?.credentials ?? "same-origin",
      path: String(input),
    });
    return new Response("[]", { status: 200 });
  });

  await transport.get("/v1/conversations?limit=50&offset=0");
  await expect(transport.get("https://example.test/v1/tasks")).rejects.toThrow(
    "origin-relative"
  );
  expect(calls).toEqual([
    {
      authorization: null,
      credentials: "omit",
      path: "/__omi/api/v1/conversations?limit=50&offset=0",
    },
  ]);
});

test("backend read adapter maps the existing conversation, memory, and task wires into Currents", async () => {
  const transport = {
    async get(path: string): Promise<unknown> {
      if (path.startsWith("/v1/conversations")) {
        return [
          {
            id: "conversation-1",
            source: "assistant",
            structured: {
              overview: "A concise summary",
              title: "A conversation",
            },
            updated_at: "2026-08-19T00:00:00.000Z",
          },
        ];
      }
      if (path.startsWith("/v1/memories")) {
        return {
          items: [{ id: "memory-1", text: "A durable memory", updatedAt: 2 }],
        };
      }
      return {
        items: [
          {
            completed: false,
            description: "A pending task",
            dueAt: null,
            id: "task-1",
            source: "assistant",
            updatedAt: 3,
          },
        ],
      };
    },
  };
  const result = await loadBackendCurrents(transport);

  expect(result.unavailable).toEqual([]);
  expect(result.items.map((item) => item.kind)).toEqual([
    "conversation",
    "task",
    "memory",
  ]);
  expect(result.items[0]).toEqual(
    expect.objectContaining({
      summary: "A concise summary",
      title: "A conversation",
    })
  );
});

test("Home includes pendant, Currents, capability state, and the bottom search dock", async () => {
  const html = await readFile(resolve(root, "index.html"), "utf8");
  expect(html).toContain("Omi pendant");
  expect(html).toContain("Currents");
  expect(html).toContain("Search Omi");
  expect(html).toContain("manifest.webmanifest");
});
