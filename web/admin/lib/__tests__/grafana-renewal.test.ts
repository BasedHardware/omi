import { expect, it } from "vitest";
import { grafanaRenewalDelay } from "../grafana-renewal";
it("renews a four-minute token one minute before API expiry", () => {
  expect(grafanaRenewalDelay(240_000, 0)).toBe(180_000);
  expect(grafanaRenewalDelay(240_000, 239_000)).toBe(1000);
  expect(grafanaRenewalDelay(240_000, 300_000)).toBe(1000);
});
