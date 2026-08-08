import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

test("native host keeps the route-shaped Ink composition", async () => {
  const source = await read("shell/Sources/OmiShell/GlassHost.swift");
  assert.match(source, /topGlass = GlassPanelView\(cornerRadius: 26\)/);
  assert.match(source, /heroGlass = GlassPanelView\(cornerRadius: 22\)/);
  assert.match(source, /contentGlass = GlassPanelView\(cornerRadius: 22\)/);
  assert.match(source, /let navToHeroGap: CGFloat = 8/);
  assert.match(source, /let heroHeight: CGFloat = 64/);
  assert.match(source, /let heroToResultsGap: CGFloat = 12/);
  assert.match(source, /if let route = value\("route"\)/);
  assert.match(source, /if let fixture = value\("qa"\)/);
  assert.match(source, /material\.material = \.hudWindow/);
  assert.match(source, /material\.blendingMode = \.behindWindow/);
  assert.match(source, /withAlphaComponent\(reduced \? 0\.98 : 0\.46\)/);
  assert.match(source, /layer\?\.shadowPath = CGPath\(roundedRect:/);
  // red-proof: collapsing Home's hero and results into one opaque plate,
  // changing the scrim, or clipping the outer shadow fails this contract.
});

test("transparent gaps remain draggable instead of becoming an invisible web canvas", async () => {
  const source = await read("shell/Sources/OmiShell/GlassHost.swift");
  const main = await read("shell/Sources/OmiShell/main.swift");
  assert.match(source, /override func hitTest\(_ point: NSPoint\)/);
  assert.match(source, /guard interactiveIslands\.contains/);
  assert.match(source, /private let webContentMask = CAShapeLayer\(\)/);
  assert.match(source, /webView\.layer\?\.mask = webContentMask/);
  assert.match(source, /let webRect = webView\.convert\(panel\.frame, from: self\)/);
  assert.match(source, /webContentMask\.path = webPath/);
  assert.match(source, /override var mouseDownCanMoveWindow: Bool \{ true \}/);
  assert.match(main, /window\.isMovableByWindowBackground = true/);
  assert.match(main, /final class TransparentWKWebView: WKWebView/);
  assert.match(main, /override var isOpaque: Bool \{ false \}/);
  assert.match(main, /webView\.layer\?\.isOpaque = false/);
  assert.match(main, /webView\.layer\?\.backgroundColor = NSColor\.clear\.cgColor/);
  assert.doesNotMatch(main, /setValue\(false, forKey: "drawsBackground"\)/);
});

test("the visible navigation island exposes a native drag lane without covering controls", async () => {
  const source = await read("shell/Sources/OmiShell/GlassHost.swift");
  assert.match(source, /final class WindowDragRegionView: NSView/);
  assert.match(source, /window\?\.performDrag\(with: event\)/);
  assert.match(source, /addSubview\(topBarDragRegion, positioned: \.above, relativeTo: webView\)/);
  assert.match(source, /let leftControlsWidth = min\(520,/);
  assert.match(source, /let rightControlsWidth: CGFloat = 150/);
  assert.match(source, /topGlass\.bounds\.width - leftControlsWidth - rightControlsWidth/);
  // red-proof: removing the overlay or expanding it across either control
  // cluster makes the reference navigation bar non-draggable or non-clickable.
});

test("scratch shell opens at the deterministic comparison frame", async () => {
  const source = await read("shell/Sources/OmiShell/main.swift");
  assert.match(source, /width: 934, height: 671/);
  assert.match(source, /window\.isRestorable = false/);
  assert.match(source, /window\.setContentSize\(contentRect\.size\)/);
  assert.match(source, /window\.isOpaque = false/);
  assert.match(source, /items\.append\(URLQueryItem\(name: "nativeGlass", value: "1"\)\)/);
  assert.match(source, /nativeGlass", value: "1"/);
  // red-proof: removing the post-content-view size lock restores the observed
  // 296 x 278 stale frame and breaks screenshot parity.
});
