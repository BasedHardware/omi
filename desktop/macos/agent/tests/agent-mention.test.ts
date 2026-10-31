import { describe, expect, it } from "vitest";
import {
  explicitProviderFrom,
  extractAgentMentions,
} from "../src/runtime/agent-mention.js";

describe("agent mention extraction", () => {
  it("names the agent a push-to-talk task asked for", () => {
    expect(explicitProviderFrom("use codex to fix the failing test")).toBe("codex");
    expect(explicitProviderFrom("hermes, summarize this repo")).toBe("hermes");
    expect(explicitProviderFrom("ask openclaw to rename the file")).toBe("openclaw");
    expect(explicitProviderFrom("have claude code open a PR")).toBe("acp");
  });

  it("returns null when no agent is named, so the kernel keeps its default", () => {
    expect(explicitProviderFrom("fix the failing test")).toBeNull();
    expect(explicitProviderFrom("")).toBeNull();
    expect(explicitProviderFrom("   ")).toBeNull();
    expect(extractAgentMentions("fix the failing test")).toEqual([]);
  });

  it("recognizes codex even though the macOS runtime has no codex adapter yet", () => {
    // The kernel rejects it as provider_unavailable, which is what turns into
    // install guidance. Silently running the default adapter would be worse.
    expect(explicitProviderFrom("get codex to review this diff")).toBe("codex");
  });

  it("matches whole words only", () => {
    expect(explicitProviderFrom("explain hermeneutics to me")).toBeNull();
    expect(explicitProviderFrom("read the codexes in the archive")).toBeNull();
    expect(explicitProviderFrom("claudette wrote this")).toBeNull();
  });

  it("is case insensitive and tolerates punctuation and @ prefixes", () => {
    expect(explicitProviderFrom("Use CODEX.")).toBe("codex");
    expect(explicitProviderFrom("@hermes please run the suite")).toBe("hermes");
    expect(explicitProviderFrom("(openclaw) take this one")).toBe("openclaw");
  });

  it("prefers the longer alias over its own prefix", () => {
    const mentions = extractAgentMentions("send it to claude code");
    expect(mentions).toHaveLength(1);
    expect(mentions[0]).toMatchObject({ adapterId: "acp", alias: "claude code" });
  });

  it("accepts the spelling variants people actually say", () => {
    expect(explicitProviderFrom("open claw should do it")).toBe("openclaw");
    expect(explicitProviderFrom("route to open-claw")).toBe("openclaw");
    expect(explicitProviderFrom("use pi mono")).toBe("pi-mono");
    expect(explicitProviderFrom("use claude-code")).toBe("acp");
  });

  it("treats a ruled-out agent as not requested", () => {
    expect(explicitProviderFrom("do not use codex for this")).toBeNull();
    expect(explicitProviderFrom("fix it without hermes")).toBeNull();
    expect(explicitProviderFrom("anything except openclaw")).toBeNull();

    const [codex] = extractAgentMentions("don't use codex");
    expect(codex).toMatchObject({ adapterId: "codex", negated: true });
  });

  it("keeps the agent the user did ask for when another is ruled out", () => {
    expect(explicitProviderFrom("don't use codex, use hermes")).toBe("hermes");
    expect(explicitProviderFrom("not claude code — openclaw")).toBe("openclaw");
  });

  it("reports every mention in the order spoken", () => {
    const mentions = extractAgentMentions("try codex, then hermes, then openclaw");
    expect(mentions.map((mention) => mention.adapterId)).toEqual([
      "codex",
      "hermes",
      "openclaw",
    ]);
    expect(mentions.map((mention) => mention.index)).toEqual(
      [...mentions.map((mention) => mention.index)].sort((left, right) => left - right),
    );
  });

  it("takes the first agent named when several are requested at once", () => {
    // Ranking between connected agents belongs to the kernel, not to a string
    // matcher. This only reports what was said.
    expect(explicitProviderFrom("try codex or hermes")).toBe("codex");
  });

  it("does not let a negation leak across a sentence boundary", () => {
    // "not" is far enough back that hermes is still a genuine request.
    expect(explicitProviderFrom("that is not what I meant. run the suite with hermes")).toBe(
      "hermes",
    );
  });
});
