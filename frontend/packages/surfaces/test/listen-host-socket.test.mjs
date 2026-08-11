import assert from "node:assert/strict";
import test, { after } from "node:test";

import { closeRenderHarness, loadProductionExport } from "./render-harness.mjs";

after(closeRenderHarness);

for (const shell of ["macos", "ios"]) {
  test(`${shell} production composition sends only the relative Listen path to its native host`, async () => {
    const createFactory = await loadProductionExport(
      "listen-host-socket.ts",
      "createProductionListenHostSocketFactory",
    );
    const posted = [];
    const channel = { postMessage(message) { posted.push(JSON.parse(message)); } };
    const host = shell === "macos"
      ? { webkit: { messageHandlers: { omiListenSocket: channel } } }
      : { omiListenSocket: channel };
    const socket = createFactory(host)("/v4/listen?language=en");
    const opened = [];
    const messages = [];
    socket.addEventListener("open", () => opened.push(true));
    socket.addEventListener("message", (event) => messages.push(event.data));

    assert.deepEqual(posted, [{ id: "listen-1", action: "open", path: "/v4/listen?language=en" }]);
    assert.equal(JSON.stringify(posted).includes("127.0.0.1:5290"), false);
    assert.equal(JSON.stringify(posted).toLowerCase().includes("authorization"), false);
    host.__omiListenSocketEvent("listen-1", { type: "open" });
    host.__omiListenSocketEvent("listen-1", { type: "message", data: "server frame" });
    assert.deepEqual(opened, [true]);
    assert.deepEqual(messages, ["server frame"]);
  });

  test(`${shell} preflight reports host state without device identifiers and exposes only advertised recovery`, async () => {
    const createProvider = await loadProductionExport(
      "listen-host-socket.ts",
      "createProductionListenHostPreflightProvider",
    );
    const posted = [];
    const channel = { postMessage(message) { posted.push(JSON.parse(message)); } };
    const host = shell === "macos"
      ? { webkit: { messageHandlers: { omiListenSocket: channel } } }
      : { omiListenSocket: channel };
    const provider = createProvider(host);
    const changed = [];
    provider.subscribe(() => changed.push(provider.snapshot()));
    const pending = provider.refresh();
    assert.deepEqual(posted, [{ id: "listen-preflight-1", action: "preflight", operation: "check" }]);
    host.__omiListenPreflightEvent("listen-preflight-1", {
      type: "preflight", requestId: "listen-preflight-1", permission: "granted",
      deviceState: "available", deviceLabel: "Default microphone", recovery: null,
    });
    await pending;
    assert.deepEqual(provider.snapshot(), {
      permission: "granted",
      device: { state: "available", label: "Default microphone" },
      recovery: null,
    });
    assert.equal(JSON.stringify(provider.snapshot()).includes("deviceId"), false);
    assert.equal(changed.length, 2, "refresh exposes checking before the native result");
  });
}
