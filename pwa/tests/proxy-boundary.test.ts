import { expect, test } from "bun:test";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import type { ProxyOptions } from "vite";
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

test("vite build config does not access local proxy identity", () => {
  const env = new Proxy<Record<string, string | undefined>>(
    {},
    {
      get(_target, property) {
        if (String(property).startsWith("OMI_LOCAL_API_")) {
          throw new Error("static build accessed local proxy identity");
        }
        return undefined;
      },
    }
  );
  const config = viteConfig({ command: "build", env });

  expect(config.server?.proxy).toBeUndefined();
  expect(config.preview?.proxy).toBeUndefined();
});

test("unconfigured vite proxy serves an unavailable backend without credentials", () => {
  const config = viteConfig({
    command: "serve",
    env: {
      OMI_LOCAL_API_TOKEN: "operator-token",
    },
  });
  const proxy = config.server?.proxy as Record<string, ProxyOptions>;
  const responseState = {
    end: (body: string) => {
      responseState.body = body;
      responseState.writableEnded = true;
    },
    headers: undefined as Record<string, string> | undefined,
    body: undefined as string | undefined,
    statusCode: undefined as number | undefined,
    writeHead: (statusCode: number, headers: Record<string, string>) => {
      responseState.statusCode = statusCode;
      responseState.headers = headers;
    },
    writableEnded: false,
  };

  const result = proxy[LOCAL_PROXY_PREFIX]?.bypass?.(
    {} as Parameters<NonNullable<ProxyOptions["bypass"]>>[0],
    responseState as unknown as Parameters<
      NonNullable<ProxyOptions["bypass"]>
    >[1],
    proxy[LOCAL_PROXY_PREFIX]
  );

  expect(result).toBe("/__omi/api-unavailable");
  expect(responseState.statusCode).toBe(503);
  expect(responseState.headers).toEqual({ "content-type": "application/json" });
  expect(responseState.body).toBe('{"error":"local_api_unavailable"}');
  expect(proxy[LOCAL_PROXY_PREFIX]?.target).toBeUndefined();
  expect(proxy[LOCAL_PROXY_PREFIX]?.headers).toBeUndefined();
});

test("configured vite proxy injects native headers outside browser code", async () => {
  const config = viteConfig({
    command: "serve",
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
