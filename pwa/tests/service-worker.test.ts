import { expect, test } from "bun:test";
import { readFile } from "node:fs/promises";

const source = await readFile(
  new URL("../public/sw.js", import.meta.url),
  "utf8"
);

test("service worker refreshes a cached shell and preserves it for offline restart", async () => {
  const listeners = new Map<string, (event: any) => void>();
  const stored = new Map<string, Response>([["/", new Response("old shell")]]);
  const pending: Promise<unknown>[] = [];
  let offline = false;
  let requests = 0;
  new Function("self", "caches", "fetch", source)(
    {
      addEventListener: (name: string, listener: (event: any) => void) =>
        listeners.set(name, listener),
      location: { origin: "https://omi.test" },
    },
    {
      match: async (request: string | { url: string }) =>
        stored
          .get(
            typeof request === "string"
              ? request
              : new URL(request.url).pathname
          )
          ?.clone(),
      open: async () => ({
        put: async (path: string, response: Response) =>
          stored.set(path, response),
      }),
    },
    async () => {
      requests += 1;
      if (offline) throw new Error("offline");
      return new Response("new shell");
    }
  );
  const dispatch = (path: string, mode = "navigate") => {
    let response: Promise<Response> | undefined;
    listeners.get("fetch")!({
      request: { method: "GET", mode, url: `https://omi.test${path}` },
      respondWith: (value: Promise<Response>) => {
        response = value;
      },
      waitUntil: (value: Promise<unknown>) => pending.push(value),
    });
    return response;
  };

  expect(await (await dispatch("/"))?.text()).toBe("new shell");
  await Promise.all(pending);
  offline = true;
  expect(await (await dispatch("/memories"))?.text()).toBe("new shell");
  expect(requests).toBe(2);
  for (const path of [
    "/v1/settings",
    "/__omi/api/v1/settings",
    "/@vite/client",
    "/src/main.ts",
  ]) {
    expect(dispatch(path, "same-origin")).toBeUndefined();
  }
});
