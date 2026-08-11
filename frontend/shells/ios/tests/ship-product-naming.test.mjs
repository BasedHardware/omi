import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.join(here, "../app");

test("the shipped iOS shell exposes only the Omi product name", () => {
  // red-proof: restore any former "proto" display, document, or MaterialApp
  // title; this assertion fails on the exact user-visible artifact.
  const dart = readFileSync(path.join(appRoot, "lib/main.dart"), "utf8");
  const html = readFileSync(path.join(appRoot, "assets/surface/index.html"), "utf8");
  const plist = readFileSync(path.join(appRoot, "ios/Runner/Info.plist"), "utf8");

  assert.match(dart, /class OmiApp extends StatelessWidget/);
  assert.match(dart, /title: 'Omi'/);
  assert.doesNotMatch(dart, /(?:webview\s+proto|class\s+ProtoApp)/i);
  assert.match(html, /<title>Omi<\/title>/);
  assert.doesNotMatch(html, /prototype/i);

  const visibleNames = [...plist.matchAll(
    /<key>(CFBundleDisplayName|CFBundleName)<\/key>\s*<string>([^<]+)<\/string>/g,
  )];
  assert.deepEqual(
    visibleNames.map((match) => [match[1], match[2]]),
    [["CFBundleDisplayName", "Omi"], ["CFBundleName", "Omi"]],
  );
});
