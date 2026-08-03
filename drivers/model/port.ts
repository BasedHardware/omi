/** Imperative edge contract. Core packages never import this module. */
export interface ModelPort {
  invoke(request: { strategy: string; version: string; input: unknown }): Promise<unknown>;
  render(request: { strategy: string; version: string; input: unknown }): Promise<{ summary_text: string; citations: readonly string[] }>;
  compose(request: { strategy: string; version: string; input: unknown }): Promise<{ answer_text: string; citations: readonly string[]; assertions: readonly { text: string; citations: readonly string[] }[] }>;
}

/** Test-only deterministic adapter; it makes no network or real-model call. */
export class DeterministicFakeModel implements ModelPort {
  constructor(private readonly response: unknown | ((request: { strategy: string; version: string; input: unknown }) => unknown)) {}
  async invoke(request: { strategy: string; version: string; input: unknown }): Promise<unknown> {
    const response = typeof this.response === "function" ? this.response(request) : this.response;
    return structuredClone(response);
  }
  async render(request: { strategy: string; version: string; input: unknown }): Promise<{ summary_text: string; citations: readonly string[] }> {
    const response = typeof this.response === "function" ? this.response(request) : this.response;
    if (typeof response === "string") return { summary_text: response, citations: [] };
    const value = response as { summary_text?: unknown; citations?: unknown };
    return { summary_text: typeof value.summary_text === "string" ? value.summary_text : "", citations: Array.isArray(value.citations) ? value.citations.filter((item): item is string => typeof item === "string") : [] };
  }
  async compose(request: { strategy: string; version: string; input: unknown }): Promise<{ answer_text: string; citations: readonly string[]; assertions: readonly { text: string; citations: readonly string[] }[] }> {
    const response = typeof this.response === "function" ? this.response(request) : this.response;
    if (typeof response === "string") return { answer_text: response, citations: [], assertions: [] };
    const value = response as { answer_text?: unknown; citations?: unknown; assertions?: unknown };
    const assertions = Array.isArray(value.assertions) ? value.assertions.flatMap((item) => {
      if (typeof item !== "object" || item === null) return [];
      const assertion = item as { text?: unknown; citations?: unknown };
      return typeof assertion.text === "string" && Array.isArray(assertion.citations) ? [{ text: assertion.text, citations: assertion.citations.filter((citation): citation is string => typeof citation === "string") }] : [];
    }) : [];
    return { answer_text: typeof value.answer_text === "string" ? value.answer_text : "", citations: Array.isArray(value.citations) ? value.citations.filter((item): item is string => typeof item === "string") : [], assertions };
  }
}
