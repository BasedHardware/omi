import assert from "node:assert/strict";
import test, { after } from "node:test";

import { closeRenderHarness, loadProductionExport } from "./render-harness.mjs";

after(closeRenderHarness);

test("production screen bridge posts fixed verbs and never invents a working control when absent", async () => {
  const createBridge = await loadProductionExport("screen-host-socket.ts", "createProductionScreenHostBridge");
  const posted = [];
  const channel = { postMessage(message) { posted.push(JSON.parse(message)); } };
  const host = { webkit: { messageHandlers: { omiScreenBridge: channel } } };
  const bridge = createBridge(host);
  assert.equal(bridge.available, true);
  const pending = bridge.refresh();
  assert.deepEqual(posted[0], { id: "screen-1", action: "screen.status", params: {} });
  host.__omiScreenBridgeEvent("screen-1", {
    state: "recording",
    permission: "granted",
    framesStored: 3,
    bytesOnDisk: 1000,
  });
  await pending;
  assert.equal(bridge.snapshot().state, "recording");
  assert.equal(bridge.snapshot().permission, "granted");
  host.__omiScreenStatusEvent({
    state: "paused",
    permission: "granted",
    framesStored: 3,
    bytesOnDisk: 1000,
  });
  assert.equal(bridge.snapshot().state, "paused");
  assert.equal(JSON.stringify(posted).toLowerCase().includes("authorization"), false);

  const absent = createBridge({});
  assert.equal(absent.available, false);
});

test("frameImage posts the shell string handle, not the HTTP FrameRef object", async () => {
  const createBridge = await loadProductionExport("screen-host-socket.ts", "createProductionScreenHostBridge");
  const posted = [];
  const channel = { postMessage(message) { posted.push(JSON.parse(message)); } };
  const host = { webkit: { messageHandlers: { omiScreenBridge: channel } } };
  const bridge = createBridge(host);
  const pending = bridge.frameImage({ frameRef: { kind: "opaque", ref: "local-frame-1" } });
  assert.deepEqual(posted[0], {
    id: "screen-1",
    action: "screen.frameImage",
    params: { frameRef: "local-frame-1" },
  });
  host.__omiScreenBridgeEvent("screen-1", { pngBase64: "QQ==", width: 2, height: 1 });
  const image = await pending;
  assert.equal(image.width, 2);
  assert.equal(image.height, 1);
});

test("malformed status pushes do not become permission-denied", async () => {
  const createBridge = await loadProductionExport("screen-host-socket.ts", "createProductionScreenHostBridge");
  const channel = { postMessage() {} };
  const host = { omiScreenBridge: channel };
  const bridge = createBridge(host);
  host.__omiScreenStatusEvent({
    state: "error",
    permission: { toString() { return "denied"; } },
    framesStored: 1,
  });
  assert.notEqual(bridge.snapshot().permission, "denied");
});
