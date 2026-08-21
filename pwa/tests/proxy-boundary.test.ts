import { expect, test } from "bun:test";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import type { ProxyOptions } from "vite";
import viteConfig from "../vite.config";
import {
  DEVELOPMENT_BACKEND_UNSUPPORTED_STATUS,
  assertLocalProxyPath,
  assertLoopbackBackendUrl,
  developmentBackendUnsupportedResponse,
  isExamplePlatformRequestSupported,
  localProxyRequestInit,
  resolveLocalBackendUrl,
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

test("development backend selection is explicit, fixed, and off by default", () => {
  expect(resolveLocalBackendUrl({}).origin).toBe("http://127.0.0.1:8787");
  expect(
    resolveLocalBackendUrl({ OMI_DEV_BACKEND: "example-platform" }).origin
  ).toBe("http://127.0.0.1:4851");
  expect(() => resolveLocalBackendUrl({ OMI_DEV_BACKEND: "legacy" })).toThrow(
    "compatible allowlisted backend"
  );
  expect(() =>
    resolveLocalBackendUrl({
      NODE_ENV: "production",
      OMI_DEV_BACKEND: "example-platform",
    })
  ).toThrow("unavailable in production");
  expect(() =>
    resolveLocalBackendUrl({
      OMI_DEV_BACKEND: "example-platform",
      OMI_LOCAL_BACKEND_URL: "http://127.0.0.1:9999",
    })
  ).toThrow("cannot be combined");
});

test("vite selects only the allowlisted example platform without browser credentials", () => {
  const config = viteConfig({
    command: "serve",
    env: {
      OMI_DEV_BACKEND: "example-platform",
      OMI_LOCAL_API_CLIENT_ID: "operator-client",
      OMI_LOCAL_API_TOKEN: "operator-token",
    },
  });
  const proxy = config.server?.proxy as Record<string, ProxyOptions>;

  expect(proxy[LOCAL_PROXY_PREFIX]?.target).toBe("http://127.0.0.1:4851");
});

test("example platform permits only candidate-compatible read routes", () => {
  expect(
    isExamplePlatformRequestSupported(
      "GET",
      "/__omi/api/v1/conversations?limit=50&offset=0"
    )
  ).toBe(true);
  expect(
    isExamplePlatformRequestSupported(
      "GET",
      "/__omi/api/v1/memories?limit=50&cursor=next"
    )
  ).toBe(true);
  for (const [method, path] of [
    ["GET", "/__omi/api/v1/tasks"],
    ["GET", "/__omi/api/v1/chat-messages?limit=50"],
    ["GET", "/__omi/api/v1/settings"],
    ["POST", "/__omi/api/v1/chat-attachments"],
    ["GET", "/__omi/api/v1/chat-generations/one/events"],
    ["DELETE", "/__omi/api/v1/chat-generations/one"],
    ["POST", "/__omi/api/v1/conversations"],
    ["GET", "/__omi/api/v1/conversations/one"],
  ]) {
    expect(isExamplePlatformRequestSupported(method, path)).toBe(false);
  }
});

test("vite refuses unsupported example platform requests with a typed error", () => {
  const config = viteConfig({
    command: "serve",
    env: {
      OMI_DEV_BACKEND: "example-platform",
      OMI_LOCAL_API_CLIENT_ID: "operator-client",
      OMI_LOCAL_API_TOKEN: "operator-token",
    },
  });
  const proxy = config.server?.proxy as Record<string, ProxyOptions>;
  const responseState = {
    body: undefined as string | undefined,
    statusCode: undefined as number | undefined,
    end(body: string) {
      responseState.body = body;
    },
    writeHead(statusCode: number) {
      responseState.statusCode = statusCode;
    },
  };
  const option = proxy[LOCAL_PROXY_PREFIX];
  const result = option?.bypass?.(
    { method: "POST", url: "/__omi/api/v1/chat-messages" } as Parameters<
      NonNullable<ProxyOptions["bypass"]>
    >[0],
    responseState as unknown as Parameters<
      NonNullable<ProxyOptions["bypass"]>
    >[1],
    option
  );

  expect(result).toBe("/__omi/api-unsupported");
  expect(responseState.statusCode).toBe(DEVELOPMENT_BACKEND_UNSUPPORTED_STATUS);
  expect(responseState.body).toBe(developmentBackendUnsupportedResponse);
  expect(JSON.parse(responseState.body ?? "")).toEqual({
    error: {
      code: "development_backend_unsupported",
      retryable: false,
      action: "none",
    },
  });
});

test("vite forwards supported example platform reads", () => {
  const config = viteConfig({
    command: "serve",
    env: {
      OMI_DEV_BACKEND: "example-platform",
      OMI_LOCAL_API_CLIENT_ID: "operator-client",
      OMI_LOCAL_API_TOKEN: "operator-token",
    },
  });
  const option = (config.server?.proxy as Record<string, ProxyOptions>)[
    LOCAL_PROXY_PREFIX
  ];
  const result = option?.bypass?.(
    {
      method: "GET",
      url: "/__omi/api/v1/memories?limit=50",
    } as Parameters<NonNullable<ProxyOptions["bypass"]>>[0],
    {} as Parameters<NonNullable<ProxyOptions["bypass"]>>[1],
    option
  );

  expect(result).toBeUndefined();
});
