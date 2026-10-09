import { createRequire } from "node:module";

import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);

describe("grafana rewrite proxy timeout", () => {
  it("outlasts Next's 30s default so slow panel queries are not aborted", () => {
    const config = require("../../next.config.js");
    // Slowest successful stats read observed through this proxy was ~317s.
    expect(config.experimental.proxyTimeout).toBeGreaterThanOrEqual(360_000);
  });
});
