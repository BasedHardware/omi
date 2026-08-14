import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.join(here, "../app");
const appIconRoot = path.join(appRoot, "ios/Runner/Assets.xcassets/AppIcon.appiconset");
const OMI_APP_ICON_SHA256 = "eff6c16e8499bd047c7b155b3d56ffae054ee1cd0cecc6e537d45a51ba575341";

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

  const contents = JSON.parse(readFileSync(path.join(appIconRoot, "Contents.json"), "utf8"));
  for (const image of contents.images) {
    if (typeof image.filename !== "string") continue;
    const bytes = readFileSync(path.join(appIconRoot, image.filename));
    assert.equal(bytes.subarray(1, 4).toString("ascii"), "PNG", `${image.filename} is a PNG`);
    assert.ok(bytes.length > 256, `${image.filename} is not an empty placeholder`);
    const points = Number.parseFloat(image.size.split("x", 1)[0]);
    const scale = Number.parseInt(image.scale, 10);
    const expectedPixels = points * scale;
    assert.equal(bytes.readUInt32BE(16), expectedPixels, `${image.filename} width matches its asset slot`);
    assert.equal(bytes.readUInt32BE(20), expectedPixels, `${image.filename} height matches its asset slot`);
  }
  const productIcon = readFileSync(path.join(appIconRoot, "Icon-App-1024x1024@1x.png"));
  assert.equal(createHash("sha256").update(productIcon).digest("hex"), OMI_APP_ICON_SHA256);
});
