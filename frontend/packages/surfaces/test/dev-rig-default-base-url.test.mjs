import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

/** True for IPv4 loopback (127.0.0.0/8), IPv6 ::1, and the localhost name. */
function isLoopbackHostname(hostname) {
  const host = hostname.replace(/^\[|\]$/g, "").toLowerCase();
  if (host === "localhost" || host === "::1") return true;
  const m = /^127\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(host);
  if (!m) return false;
  return m.slice(1).every((octet) => Number(octet) <= 255);
}

function fallbackBaseUrl(source) {
  // A previously stored value must still win — only the ?? fallback is the default.
  const match = source.match(/useState\(localStorage\.getItem\(LS_URL\) \?\? "([^"]+)"\)/);
  assert.ok(
    match,
    "dev rig must default base URL via localStorage.getItem(LS_URL) ?? \"…\"",
  );
  return match[1];
}

test("dev rig default base URL is a loopback host", async () => {
  const source = await read("src/dev/main.tsx");
  const fallback = fallbackBaseUrl(source);
  let url;
  try {
    url = new URL(fallback);
  } catch {
    assert.fail(`dev rig default base URL must be a valid absolute URL, got ${JSON.stringify(fallback)}`);
  }
  assert.ok(
    isLoopbackHostname(url.hostname),
    `dev rig default base URL must be a loopback host, got ${url.hostname}`,
  );
  // red-proof: restore "https://api.omi.me" (or any non-loopback host) as the
  // useState LS_URL fallback — isLoopbackHostname fails on the hostname.
});
