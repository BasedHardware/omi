import { describe, expect, it } from "vitest";
import {
  adapterCapabilitiesFor,
  PRODUCTION_ADAPTER_IDS,
  type ProductionAdapterId,
} from "../src/adapters/interface.js";
import {
  scoreAdapters,
  selectAdapterChain,
  selectRequestedAdapterChain,
  type AdapterCandidate,
} from "../src/runtime/adapter-scoring.js";

/** Candidates built from the real capability matrix, not invented capabilities. */
function candidates(...adapterIds: ProductionAdapterId[]): AdapterCandidate[] {
  return adapterIds.map((adapterId) => ({
    adapterId,
    capabilities: adapterCapabilitiesFor(adapterId),
  }));
}

const ALL_CONNECTED = candidates(...PRODUCTION_ADAPTER_IDS);

describe("adapter scoring and fallback order", () => {
  it("still lands on the current default when nothing distinguishes the agents", () => {
    // The safety property of this whole change: a runtime with no task
    // requirements must select exactly what it selects today.
    expect(selectAdapterChain(ALL_CONNECTED)[0]).toBe("acp");
    expect(selectAdapterChain(candidates("openclaw", "hermes", "acp"))[0]).toBe("acp");
  });

  it("rules out an agent that cannot do the job, using the real matrix", () => {
    // OpenClaw reports supportsTools: false, so a tool-using task must not
    // select it — and must not fall back to it either.
    expect(adapterCapabilitiesFor("openclaw").supportsTools).toBe(false);

    const chain = selectAdapterChain(candidates("openclaw", "hermes"), {
      needsTools: true,
    });
    expect(chain).toEqual(["hermes"]);
    expect(chain).not.toContain("openclaw");
  });

  it("explains why an agent was skipped", () => {
    const [openclaw] = scoreAdapters(candidates("openclaw"), { needsTools: true });

    expect(openclaw.eligible).toBe(false);
    expect(openclaw.missing).toContain("tool support");
    expect(openclaw.reasons.join(" ")).toContain("ineligible");
  });

  it("ranks every eligible agent so there is something to fall back to", () => {
    const chain = selectAdapterChain(ALL_CONNECTED, { needsTools: true });

    expect(chain.length).toBeGreaterThan(1);
    expect(chain[0]).toBe("acp");
    expect(new Set(chain).size).toBe(chain.length);
  });

  it("puts the agent the user asked for first, keeping the rest as fallback", () => {
    const chain = selectRequestedAdapterChain(ALL_CONNECTED, "hermes", {
      needsTools: true,
    });

    expect(chain[0]).toBe("hermes");
    expect(chain.slice(1)).toContain("acp");
    expect(new Set(chain).size).toBe(chain.length);
  });

  it("leaves the ranked chain alone when the requested agent is not connected", () => {
    // Lets the caller tell "not connected" (chain unchanged) apart from
    // "connected but not chosen", so it can answer with install guidance.
    const connected = candidates("acp", "hermes");
    const chain = selectRequestedAdapterChain(connected, "codex", { needsTools: true });

    expect(chain).toEqual(selectAdapterChain(connected, { needsTools: true }));
    expect(chain).not.toContain("codex");
  });

  it("prefers an agent that can resume when the task may be resumed", () => {
    const scored = scoreAdapters(ALL_CONNECTED, { prefersResume: true });
    const winner = scored.find((entry) => entry.eligible);

    expect(winner).toBeDefined();
    expect(adapterCapabilitiesFor(winner!.adapterId).supportsNativeResume).toBe(true);
    expect(winner!.reasons).toContain("resumes natively");
  });

  it("keeps a preference from outranking a hard requirement", () => {
    // A cancellable agent that cannot use tools still loses a tool-using task.
    const chain = selectAdapterChain(candidates("openclaw", "acp"), {
      needsTools: true,
      prefersCancellation: true,
    });

    expect(chain[0]).toBe("acp");
    expect(chain).not.toContain("openclaw");
  });

  it("scores an empty or single-agent runtime without special cases", () => {
    expect(selectAdapterChain([])).toEqual([]);
    expect(selectAdapterChain(candidates("hermes"))).toEqual(["hermes"]);
    expect(selectAdapterChain(candidates("openclaw"), { needsTools: true })).toEqual([]);
  });

  it("sorts an unknown adapter last instead of throwing", () => {
    const unknown: AdapterCandidate = {
      adapterId: "future-agent" as ProductionAdapterId,
      capabilities: adapterCapabilitiesFor("acp"),
    };
    const chain = selectAdapterChain([unknown, ...candidates("acp")], {
      needsTools: true,
    });

    expect(chain[0]).toBe("acp");
    expect(chain).toContain("future-agent");
  });
});
