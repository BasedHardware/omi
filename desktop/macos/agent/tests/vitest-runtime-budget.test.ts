import { describe, expect, it } from "vitest";

import config from "../vitest.config";

describe("Vitest runtime budget", () => {
  it("keeps contention-sensitive agent tests bounded without using Vitest defaults", () => {
    expect(config.test?.testTimeout).toBe(15_000);
    expect(config.test?.hookTimeout).toBe(20_000);
  });
});
