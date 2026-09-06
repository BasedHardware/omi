import assert from "node:assert/strict";
import { startMetro } from "./start-metro";

const metro = await startMetro(0);
try {
  const address = metro.server.address();
  assert(address !== null && typeof address !== "string");
  const response = await fetch(`http://127.0.0.1:${address.port}/status`, {
    signal: AbortSignal.timeout(5000),
  });
  assert.equal(response.status, 200);
  assert.equal(await response.text(), "packager-status:running");
  console.log("Bun Metro startup passed");
} finally {
  await metro.stop();
}
