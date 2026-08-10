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
}
