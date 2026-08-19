import { expect, test } from "bun:test";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import viteConfig from "../vite.config";
import {
  assertLocalProxyPath,
  assertLoopbackBackendUrl,
  localProxyRequestInit,
  rewriteLocalProxyPath,
  LOCAL_PROXY_PREFIX,
} from "../../react-native/src/local-proxy";

const root = resolve(import.meta.dir, "..");

test("browser proxy accepts only origin-relative local API paths", () => {
  expect(assertLocalProxyPath("/__omi/api/v1/settings?cursor=1")).toBe(
    "/__omi/api/v1/settings?cursor=1"
  );
  expect(rewriteLocalProxyPath("/__omi/api/v1/settings")).toBe("/v1/settings");
  expect(() =>
    assertLocalProxyPath("https://example.com/v1/settings")
  ).toThrow();
  expect(() => assertLocalProxyPath("/v1/settings")).toThrow();
});

test("browser proxy refuses credential-bearing headers", () => {
  expect(() =>
    localProxyRequestInit({ headers: { Authorization: "Bearer secret" } })
  ).toThrow("authorization");
  expect(() =>
    localProxyRequestInit({ headers: { cookie: "session=secret" } })
  ).toThrow("cookie");
  expect(() =>
    localProxyRequestInit({ headers: { "x-omi-client-id": "client" } })
  ).toThrow("x-omi-client-id");
  expect(() =>
    localProxyRequestInit({ headers: { "x-omi-contract-version": "1.0.0" } })
  ).toThrow("x-omi-contract-version");
});

test("browser proxy applies the native JSON body policy", () => {
  const init = localProxyRequestInit({
    body: '{"text":"hello"}',
    headers: { "content-type": "text/plain" },
  });

  expect(new Headers(init.headers).get("content-type")).toBe(
    "application/json"
  );
  expect(init.credentials).toBe("omit");
});

test("vite proxy refuses to start without an operator client id", () => {
  expect(() =>
    viteConfig({
      env: {
        OMI_LOCAL_API_TOKEN: "operator-token",
      },
    })
  ).toThrow("OMI_LOCAL_API_CLIENT_ID");
});

test("configured vite proxy injects native headers outside browser code", async () => {
  const config = viteConfig({
    env: {
      OMI_LOCAL_API_CLIENT_ID: "operator-client",
      OMI_LOCAL_API_TOKEN: "operator-token",
    },
  });
  const proxy = config.server?.proxy as Record<
    string,
    { headers?: Record<string, string> }
  >;
  const webSource = await readFile(
    resolve(root, "../react-native/src/omiNative.web.ts"),
    "utf8"
  );

  expect(proxy[LOCAL_PROXY_PREFIX]?.headers).toEqual({
    authorization: "Bearer operator-token",
    "x-omi-client-id": "operator-client",
    "x-omi-contract-version": "1.0.0",
  });
  expect(webSource).not.toContain("OMI_LOCAL_API_CLIENT_ID");
  expect(webSource).not.toContain("Bearer operator-token");
});

test("vite backend target is loopback-only", () => {
  expect(assertLoopbackBackendUrl("http://127.0.0.1:8787").hostname).toBe(
    "127.0.0.1"
  );
  expect(assertLoopbackBackendUrl("http://[::1]:8787").hostname).toBe("[::1]");
  expect(() => assertLoopbackBackendUrl("https://example.com")).toThrow();
  expect(() =>
    assertLoopbackBackendUrl("http://user:pass@127.0.0.1:8787")
  ).toThrow();
});
