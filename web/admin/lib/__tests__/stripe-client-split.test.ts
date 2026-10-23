import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Pins the read/write client split in lib/stripe: read-only paths must use the
 * restricted STRIPE_READ_API_KEY client when that key is set, fall back to the
 * full key at most with a one-time warning, and keep the full-key client for
 * the one Stripe write (affiliate transfers).
 */

const ctorKeys = vi.hoisted(() => [] as string[]);

class MockStripe {
  constructor(public key: string) {
    ctorKeys.push(key);
  }
}

vi.mock("stripe", () => ({ default: MockStripe }));

const root = path.resolve(process.cwd());

async function freshStripeLib() {
  vi.resetModules();
  return import("../stripe");
}

beforeEach(() => {
  ctorKeys.length = 0;
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("getOptionalStripeRead / getStripeRead", () => {
  it("construct the read client from STRIPE_READ_API_KEY when it is set", async () => {
    vi.stubEnv("STRIPE_READ_API_KEY", "rk_test_read_only");
    vi.stubEnv("STRIPE_SECRET_KEY", "sk_test_full");
    const lib = await freshStripeLib();

    const read = lib.getOptionalStripeRead();
    expect(read).toBeInstanceOf(MockStripe);
    expect((read as unknown as MockStripe).key).toBe("rk_test_read_only");

    // the full-key client stays separate, on its own key
    const full = lib.getStripe();
    expect((full as unknown as MockStripe).key).toBe("sk_test_full");
    expect(full).not.toBe(read);

    // both clients are cached; no extra constructions on repeated calls
    expect(lib.getOptionalStripeRead()).toBe(read);
    expect(lib.getStripe()).toBe(full);
    expect(ctorKeys).toEqual(["rk_test_read_only", "sk_test_full"]);
  });

  it("do not warn when the read key is set", async () => {
    vi.stubEnv("STRIPE_READ_API_KEY", "rk_test_read_only");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const lib = await freshStripeLib();

    lib.getOptionalStripeRead();
    expect(warn).not.toHaveBeenCalled();
  });

  it("fall back to the full key with a one-time warning when the read key is unset", async () => {
    vi.stubEnv("STRIPE_SECRET_KEY", "sk_test_full");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const lib = await freshStripeLib();

    const first = lib.getOptionalStripeRead();
    const second = lib.getOptionalStripeRead();
    expect((first as unknown as MockStripe).key).toBe("sk_test_full");
    expect(second).toBe(first);

    expect(warn).toHaveBeenCalledTimes(1);
    expect(warn.mock.calls[0][0]).toContain("STRIPE_READ_API_KEY");
  });

  it("return null and stay quiet when no Stripe key is set at all", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const lib = await freshStripeLib();

    expect(lib.getOptionalStripeRead()).toBeNull();
    expect(warn).not.toHaveBeenCalled();

    expect(() => lib.getStripeRead()).toThrow(/STRIPE_READ_API_KEY/);
    expect(() => lib.getStripeRead()).toThrow(/STRIPE_SECRET_KEY/);
  });
});

describe("route/lib usage of the full-key client", () => {
  function tsFiles(directory: string): string[] {
    return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
      // tests may name either accessor in mocks and prose; only production
      // sources are under the least-privilege contract
      if (entry.name === "__tests__" || entry.name === "node_modules")
        return [];
      if (entry.isDirectory()) return tsFiles(path.join(directory, entry.name));
      if (/\.test\.tsx?$/.test(entry.name)) return [];
      return /\.(ts|tsx)$/.test(entry.name)
        ? [path.join(directory, entry.name)]
        : [];
    });
  }

  it("is restricted to lib/stripe.ts (definition) and the affiliate-payouts write route", () => {
    // getStripe/getOptionalStripe build a client on the FULL live key; every
    // read-only consumer must go through getStripeRead/getOptionalStripeRead.
    const allowed = new Set([
      path.resolve(root, "lib/stripe.ts"),
      path.resolve(root, "app/api/omi/affiliate-payouts/route.ts"),
    ]);
    const offenders: string[] = [];
    for (const file of [
      ...tsFiles(path.resolve(root, "app")),
      ...tsFiles(path.resolve(root, "lib")),
    ]) {
      if (allowed.has(file)) continue;
      const source = readFileSync(file, "utf8");
      if (/\bgetStripe\b|\bgetOptionalStripe\b/.test(source))
        offenders.push(file);
    }
    expect(offenders).toEqual([]);
  });
});
