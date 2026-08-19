import { fileURLToPath } from "node:url";
import {
  assertLoopbackBackendUrl,
  LOCAL_PROXY_PREFIX,
  rewriteLocalProxyPath,
} from "../react-native/src/local-proxy.ts";

const reactNativeWebPath = fileURLToPath(
  new URL("../node_modules/react-native-web", import.meta.url)
);

type LocalProxyEnvironment = Record<string, string | undefined>;

export function localProxy(environment: LocalProxyEnvironment = process.env) {
  const target = assertLoopbackBackendUrl(
    environment.OMI_LOCAL_BACKEND_URL ?? "http://127.0.0.1:8787"
  ).origin;
  const token = environment.OMI_LOCAL_API_TOKEN?.trim();
  const clientId = environment.OMI_LOCAL_API_CLIENT_ID?.trim();
  if (clientId === undefined || clientId === "") {
    throw new Error(
      "OMI_LOCAL_API_CLIENT_ID is required for the local API proxy"
    );
  }
  if (token === undefined || token === "") {
    throw new Error("OMI_LOCAL_API_TOKEN is required for the local API proxy");
  }
  return {
    target,
    changeOrigin: false,
    rewrite: rewriteLocalProxyPath,
    headers: {
      authorization: `Bearer ${token}`,
      "x-omi-client-id": clientId,
      "x-omi-contract-version": "1.0.0",
    },
  };
}

export default ({
  env = process.env,
}: { env?: LocalProxyEnvironment } = {}) => {
  const proxy = { [LOCAL_PROXY_PREFIX]: localProxy(env) };
  return {
    build: {
      emptyOutDir: true,
      outDir: "dist",
      target: "es2022",
    },
    preview: {
      host: "127.0.0.1",
      proxy,
    },
    resolve: {
      alias: { "react-native": reactNativeWebPath },
      dedupe: [
        "@react-native/assets-registry",
        "react",
        "react-native-svg",
        "react-native-web",
      ],
      extensions: [
        ".web.ts",
        ".web.tsx",
        ".web.js",
        ".web.jsx",
        ".mjs",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".json",
      ],
      preserveSymlinks: true,
    },
    server: {
      host: "127.0.0.1",
      proxy,
    },
  };
};
