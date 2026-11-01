import { createRequire } from "node:module";

import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);

describe("legacy Grafana proxy", () => {
  it("does not configure a same-origin rewrite or proxy timeout", () => {
    const config = require("../../next.config.js");
    expect(config.rewrites).toBeUndefined();
    expect(config.experimental?.proxyTimeout).toBeUndefined();
  });
});
