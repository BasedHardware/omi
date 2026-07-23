import { createServer } from "node:net";
import { writeFile } from "node:fs/promises";

const LOOPBACK_HOST = "127.0.0.1";

export async function allocateLoopbackPort() {
  return await new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, LOOPBACK_HOST, () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        reject(new Error("Could not allocate a loopback emulator port"));
        return;
      }
      server.close((error) => (error ? reject(error) : resolve(address.port)));
    });
  });
}

export async function writeEmulatorConfig(configPath) {
  const [port, websocketPort] = await Promise.all([allocateLoopbackPort(), allocateLoopbackPort()]);
  if (port === websocketPort) {
    throw new Error("Firestore API and websocket ports must be distinct");
  }

  await writeFile(
    configPath,
    `${JSON.stringify({ emulators: { firestore: { host: LOOPBACK_HOST, port, websocketPort } } })}\n`,
  );
  return { port, websocketPort };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const [configPath] = process.argv.slice(2);
  if (!configPath) {
    throw new Error("Usage: emulator_config.mjs <firebase.json path>");
  }
  const { port, websocketPort } = await writeEmulatorConfig(configPath);
  process.stdout.write(`${port} ${websocketPort}\n`);
}
