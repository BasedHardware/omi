import { fileURLToPath } from "node:url";
import type { ConfigEnv, ProxyOptions } from "vite";
import {
  DEVELOPMENT_BACKEND_UNSUPPORTED_STATUS,
  LOCAL_PROXY_PREFIX,
  developmentBackendUnsupportedResponse,
  isExamplePlatformRequestSupported,
  isExamplePlatformSelection,
  resolveLocalBackendUrl,
  rewriteLocalProxyPath,
} from "../react-native/src/local-proxy.ts";

const reactNativeWebPath = fileURLToPath(
  new URL("../node_modules/react-native-web", import.meta.url)
);

type LocalProxyEnvironment = Record<string, string | undefined>;

const unavailableBackendResponse = JSON.stringify({
  error: "local_api_unavailable",
});

export function localProxy(
  environment: LocalProxyEnvironment = process.env
): ProxyOptions {
  const target = resolveLocalBackendUrl(environment).origin;
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
    ...(isExamplePlatformSelection(environment)
      ? {
          bypass(request, response) {
            if (
              isExamplePlatformRequestSupported(request.method, request.url)
            ) {
              return;
            }
            if (response === undefined) {
              return false;
            }
            response.writeHead(DEVELOPMENT_BACKEND_UNSUPPORTED_STATUS, {
              "content-type": "application/json",
            });
            response.end(developmentBackendUnsupportedResponse);
            return "/__omi/api-unsupported";
          },
        }
      : {}),
    headers: {
      authorization: `Bearer ${token}`,
      "x-omi-client-id": clientId,
      "x-omi-contract-version": "1.0.0",
    },
  };
}

function unavailableLocalProxy(): ProxyOptions {
  return {
    bypass(_request, response) {
      if (response === undefined) {
        return false;
      }
      response.writeHead(503, { "content-type": "application/json" });
      response.end(unavailableBackendResponse);
      return "/__omi/api-unavailable";
    },
  };
}

function serverProxy(environment: LocalProxyEnvironment): ProxyOptions {
  const clientId = environment.OMI_LOCAL_API_CLIENT_ID?.trim();
  const token = environment.OMI_LOCAL_API_TOKEN?.trim();
  if (
    clientId === undefined ||
    clientId === "" ||
    token === undefined ||
    token === ""
  ) {
    return unavailableLocalProxy();
  }
  return localProxy(environment);
}

export default ({
  command,
  env,
}: Pick<ConfigEnv, "command"> & { env?: LocalProxyEnvironment }) => {
  const proxy =
    command === "serve"
      ? { [LOCAL_PROXY_PREFIX]: serverProxy(env ?? process.env) }
      : undefined;
  return {
    build: {
      emptyOutDir: true,
      outDir: "dist",
      target: "es2022",
    },
    preview: {
      host: "127.0.0.1",
      ...(proxy === undefined ? {} : { proxy }),
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
      ...(proxy === undefined ? {} : { proxy }),
    },
  };
};
