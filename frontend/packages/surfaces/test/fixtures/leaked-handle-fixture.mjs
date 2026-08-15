import net from "node:net";
import test from "node:test";

// Intentionally leaks a TCP listener after the test body finishes.
// hang-guard.test.mjs spawns this file to prove the hang guard fails red.
test("leaks a TCP listener after the test body finishes", async () => {
  const server = net.createServer();
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
});
