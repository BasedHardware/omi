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
      deviceState: "available", deviceLabel: { toString() { throw new Error("hostile getter"); } }, recovery: null,
    });
    assert.equal(provider.snapshot().permission, "unavailable", "malformed host state fails closed");
    const valid = provider.refresh();
    assert.deepEqual(posted[1], { id: "listen-preflight-2", action: "preflight", operation: "check" });
    host.__omiListenPreflightEvent("listen-preflight-2", {
      type: "preflight", requestId: "listen-preflight-2", permission: "granted",
      deviceState: "available", deviceLabel: "Default microphone", recovery: null,
    });
    await pending;
    await valid;
    const ready = provider.snapshot();
    assert.ok(Object.isFrozen(ready));
    assert.ok(Object.isFrozen(ready.device));
    assert.throws(() => { ready.permission = "denied"; }, TypeError);
    assert.deepEqual(provider.snapshot(), {
      permission: "granted",
      device: { state: "available", label: "Default microphone" },
      recovery: null,
    });
    assert.equal(JSON.stringify(provider.snapshot()).includes("deviceId"), false);
    assert.equal(changed.length, 4, "refreshes expose checking and fail-closed transitions");
  });

  test(`${shell} preflight rejects accessor-backed host replies without invoking getters`, async () => {
    const createProvider = await loadProductionExport(
      "listen-host-socket.ts",
      "createProductionListenHostPreflightProvider",
    );
    const channel = { postMessage() {} };
    const host = shell === "macos"
      ? { webkit: { messageHandlers: { omiListenSocket: channel } } }
      : { omiListenSocket: channel };
    const provider = createProvider(host);
    const pending = provider.refresh();
    let touched = false;
    const hostile = Object.create(Object.prototype, {
      type: { value: "preflight", enumerable: true },
      requestId: { value: "listen-preflight-1", enumerable: true },
      permission: { get() { touched = true; throw new Error("getter executed"); }, enumerable: true },
      deviceState: { value: "available", enumerable: true },
    });
    host.__omiListenPreflightEvent("listen-preflight-1", hostile);
    await pending;
    assert.equal(touched, false, "parser reads own data descriptors only");
    assert.equal(provider.snapshot().permission, "unavailable", "accessor-backed state fails closed");
  });

  test(`${shell} preflight rejects Proxy-wrapped host replies without accepting forged readiness`, async () => {
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
    const pending = provider.refresh();
    const valid = {
      type: "preflight", requestId: "listen-preflight-1", permission: "granted",
      deviceState: "available", deviceLabel: "Default microphone", recovery: null,
    };
    host.__omiListenPreflightEvent("listen-preflight-1", new Proxy(valid, {}));
    await pending;
    assert.equal(provider.snapshot().permission, "unavailable", "Proxy host state fails closed");
    assert.equal(provider.snapshot().device.state, "unavailable");
    assert.equal(posted[0]?.operation, "check");
  });
}
