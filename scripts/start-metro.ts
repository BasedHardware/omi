import { createServer } from "node:http";
import { dirname, resolve } from "node:path";
import { parseArgs } from "node:util";

export async function startMetro(port: number, host = "127.0.0.1") {
  const { default: loadConfig } = require("@react-native-community/cli-config");
  const loadMetroConfig = require(resolve(
    dirname(require.resolve("@react-native/community-cli-plugin/package.json")),
    "dist/utils/loadMetroConfig.js"
  )).default;
  const projectRoot = resolve(import.meta.dir, "../react-native");
  const context = await loadConfig({ projectRoot });
  const config = await loadMetroConfig(context, { port, maxWorkers: 2 });
  const { middleware, attachHmrServer, end } =
    await require("metro").createConnectMiddleware(config);
  const app = require("connect")();
  const community =
    require("@react-native-community/cli-server-api").createDevServerMiddleware(
      {
        host,
        port,
        watchFolders: config.watchFolders,
      }
    );
  app.use(community.middleware);
  app.use(middleware);
  const server = createServer(app);
  attachHmrServer(server);
  try {
    await new Promise<void>((resolve, reject) => {
      server.once("error", reject);
      server.listen({ port, host }, resolve);
    });
  } catch (error) {
    await end();
    throw error;
  }
  return {
    server,
    stop: async () => {
      await new Promise<void>((resolve) => server.close(() => resolve()));
      await end();
    },
  };
}

if (import.meta.main) {
  const { values } = parseArgs({
    args: process.argv.slice(2),
    options: { port: { type: "string", default: "8081" } },
  });
  const port = Number(values.port);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("Metro port must be between 1 and 65535");
  }
  await startMetro(port);
  console.log(`Metro listening at http://127.0.0.1:${port}`);
}
