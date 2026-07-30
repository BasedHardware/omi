/** Imperative edge contract. Core packages never import this module. */
export interface ModelPort {
  invoke(request: { strategy: string; version: string; input: unknown }): Promise<unknown>;
}

/** Test-only deterministic adapter; it makes no network or real-model call. */
export class DeterministicFakeModel implements ModelPort {
  constructor(private readonly response: unknown) {}
  async invoke(): Promise<unknown> { return structuredClone(this.response); }
}
