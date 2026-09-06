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
  for (const platform of ["macos", "ios", "android"]) {
    const bundleResponse = await fetch(
      `http://127.0.0.1:${address.port}/index.bundle?platform=${platform}&dev=true&lazy=true&minify=false`,
      { signal: AbortSignal.timeout(60000) }
    );
    assert.equal(bundleResponse.status, 200);
    const bundle = await bundleResponse.text();
    const runtime =
      platform === "macos" ? "react-native-macos" : "react-native";
    const initialization = bundle.match(
      new RegExp(
        `\\},(\\d+),\\[[^\\n]*\\],"[^"\\n]*node_modules/${runtime}/Libraries/Core/InitializeCore\\.js"\\);`
      )
    );
    assert(
      initialization,
      `${platform} bundle contains its native initializer`
    );
    const runs = [...bundle.matchAll(/^__r\((\d+)\);$/gm)].map(
      (match) => match[1]
    );
    assert(runs.length >= 2, `${platform} initializes before the app entry`);
    assert.equal(
      runs[0],
      initialization[1],
      `${platform} runs its native initializer first`
    );
  }
  console.log("Bun Metro startup passed");
} finally {
  await metro.stop();
}
