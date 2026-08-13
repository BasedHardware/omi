export interface ModelPromptCoordinates {
  readonly provider_version: string;
  readonly model_version: string;
  readonly adapter_version: string;
  readonly strategy_version: string;
  readonly prompt_version: string;
  readonly parser_schema_version: string;
  readonly policy_version: string;
  readonly retry_version: string;
  readonly sampling_tool_version: string;
  readonly cache_format_version: "qa-model-verdict-cache-v2";
}

/** Digest-only identity for the exact initial bytes an adapter would send. */
export interface ModelInitialPromptIdentity {
  readonly prompt_digest: string;
  readonly coordinates: ModelPromptCoordinates;
}

/**
 * Metadata returned only to the QA cache wrapper. A repaired attempt has a
 * different successful prompt digest and is deliberately not initial-prompt
 * cacheable.
 */
export interface ModelInvocationSuccess {
  readonly result: unknown;
  readonly successful_prompt_digest: string;
  readonly attempt: number;
}

export type CachedModelResultValidation =
  | { readonly ok: true; readonly result: unknown }
  | { readonly ok: false };

export interface ModelInvokeRequest {
  readonly strategy: string;
  readonly version: string;
  readonly input: unknown;
  /** Cancels provider work when the external resource lease is lost. */
  readonly signal?: AbortSignal;
}

export interface ModelRenderRequest extends ModelInvokeRequest {}
export interface ModelComposeRequest extends ModelInvokeRequest {}

/** Imperative edge contract. Core packages never import this module. */
export interface ModelPort {
  invoke(request: ModelInvokeRequest): Promise<unknown>;
  /** Renders initial request identity without exposing prompt bytes. */
  initialPromptIdentity?(request: ModelInvokeRequest): ModelInitialPromptIdentity | undefined;
  /** Optional exact-success metadata for safe QA cache admission. */
  invokeWithMetadata?(request: ModelInvokeRequest): Promise<ModelInvocationSuccess>;
  /** Adapter-owned revalidation of a decoded QA cache value. */
  validateCachedResult?(request: ModelInvokeRequest, candidate: unknown): CachedModelResultValidation;
  render(request: ModelRenderRequest): Promise<{ summary_text: string; citations: readonly string[] }>;
  compose(request: ModelComposeRequest): Promise<{ answer_text: string; citations: readonly string[]; assertions: readonly { text: string; citations: readonly string[] }[] }>;
}

/** Bind one external resource-lease lifetime without changing core call sites. */
export const bindModelPortAbortSignal = (model: ModelPort, signal: AbortSignal): ModelPort => {
  if (!(signal instanceof AbortSignal)) throw new TypeError("invalid_model_abort_signal");
  const bind = <Request extends ModelInvokeRequest>(request: Request): Request =>
    Object.freeze({ ...request, signal }) as Request;
  return Object.freeze({
    invoke: (request: ModelInvokeRequest) => model.invoke(bind(request)),
    render: (request: ModelRenderRequest) => model.render(bind(request)),
    compose: (request: ModelComposeRequest) => model.compose(bind(request)),
    ...(model.initialPromptIdentity ? {
      initialPromptIdentity: (request: ModelInvokeRequest) => model.initialPromptIdentity!(bind(request)),
    } : {}),
    ...(model.invokeWithMetadata ? {
      invokeWithMetadata: (request: ModelInvokeRequest) => model.invokeWithMetadata!(bind(request)),
    } : {}),
    ...(model.validateCachedResult ? {
      validateCachedResult: (request: ModelInvokeRequest, candidate: unknown) =>
        model.validateCachedResult!(bind(request), candidate),
    } : {}),
  });
};

/** Test-only deterministic adapter; it makes no network or real-model call. */
export class DeterministicFakeModel implements ModelPort {
  constructor(private readonly response: unknown | ((request: ModelInvokeRequest) => unknown)) {}
  async invoke(request: ModelInvokeRequest): Promise<unknown> {
    const response = typeof this.response === "function" ? this.response(request) : this.response;
    return structuredClone(response);
  }
  async render(request: ModelRenderRequest): Promise<{ summary_text: string; citations: readonly string[] }> {
    const response = typeof this.response === "function" ? this.response(request) : this.response;
    if (typeof response === "string") return { summary_text: response, citations: [] };
    const value = response as { summary_text?: unknown; citations?: unknown };
    return { summary_text: typeof value.summary_text === "string" ? value.summary_text : "", citations: Array.isArray(value.citations) ? value.citations.filter((item): item is string => typeof item === "string") : [] };
  }
  async compose(request: ModelComposeRequest): Promise<{ answer_text: string; citations: readonly string[]; assertions: readonly { text: string; citations: readonly string[] }[] }> {
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
