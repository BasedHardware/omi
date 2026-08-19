import { createRequire } from "node:module";
import { dirname } from "node:path";
import {
  assertLoopbackBackendUrl,
  LOCAL_PROXY_PREFIX,
  rewriteLocalProxyPath,
} from "./src/local-proxy.ts";

const require = createRequire(import.meta.url);
const reactNativeWebPath = dirname(
  require.resolve("react-native-web/package.json")
);

function localProxy() {
  const target = assertLoopbackBackendUrl(
    process.env.OMI_LOCAL_BACKEND_URL ?? "http://127.0.0.1:8787"
  ).origin;
  const token = process.env.OMI_LOCAL_API_TOKEN?.trim();
  return {
    target,
    changeOrigin: false,
    rewrite: rewriteLocalProxyPath,
    ...(token === undefined || token === ""
      ? {}
      : { headers: { authorization: `Bearer ${token}` } }),
  };
}

export default () => {
  const proxy = { [LOCAL_PROXY_PREFIX]: localProxy() };
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
      alias: [{ find: /^react-native$/, replacement: reactNativeWebPath }],
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
    },
    server: {
      host: "127.0.0.1",
      proxy,
    },
  };
};
