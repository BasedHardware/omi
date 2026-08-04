import { describe, expect, it } from "vitest";
import { moduleEnabled, parseEdgeModules, resolveFeatures } from "../src/features.js";

describe("feature gates", () => {
  it("defaults to health+whoami", () => {
    const m = parseEdgeModules(undefined);
    expect([...m].sort()).toEqual(["health", "whoami"]);
  });

  it("parses list", () => {
    const m = parseEdgeModules("health,memory,search");
    expect(m.has("memory")).toBe(true);
    expect(m.has("whoami")).toBe(false);
  });

  it("star enables all modules", () => {
    const m = parseEdgeModules("*");
    expect(m.has("health")).toBe(true);
    expect(m.has("memory")).toBe(true);
    expect(m.has("search")).toBe(true);
    expect(m.size).toBe(7);
  });

  it("resolveFeatures proxy default on", () => {
    const f = resolveFeatures({ FIREBASE_PROJECT_ID: "p", ORIGIN_API_BASE: "https://x" });
    expect(f.proxyOrigin).toBe(true);
    expect(moduleEnabled(f, "health")).toBe(true);
  });

  it("EDGE_PROXY_ORIGIN=false", () => {
    const f = resolveFeatures({ EDGE_PROXY_ORIGIN: "false" });
    expect(f.proxyOrigin).toBe(false);
  });
});
