import type { Degraded, FallbackRecord, FallbackSink } from "@omi-core/contracts";

/**
 * The ONLY way a Degraded<T> comes into existence. Requiring the sink here is
 * the whole invariant: no fallback value without its telemetry event. The
 * cast below is the single sanctioned bypass of the brand in the entire
 * codebase; adding another is a review-blocking offense.
 */
export function degrade<T>(sink: FallbackSink, fallback: FallbackRecord, value: T): Degraded<T> {
  sink.record(fallback);
  return { value, fallback } as Degraded<T>;
}
