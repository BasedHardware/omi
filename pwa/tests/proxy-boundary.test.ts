import { expect, test } from "bun:test";
import {
  assertLocalProxyPath,
  assertLoopbackBackendUrl,
  localProxyRequestInit,
  rewriteLocalProxyPath,
} from "../src/local-proxy";

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
});

test("vite backend target is loopback-only and credential-free", () => {
  expect(assertLoopbackBackendUrl("http://127.0.0.1:8787").hostname).toBe(
    "127.0.0.1"
  );
  expect(assertLoopbackBackendUrl("http://[::1]:8787").hostname).toBe("[::1]");
  expect(() => assertLoopbackBackendUrl("https://example.com")).toThrow();
  expect(() =>
    assertLoopbackBackendUrl("http://user:pass@127.0.0.1:8787")
  ).toThrow();
});
