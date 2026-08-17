/**
 * The fallback-telemetry contract — program invariant INV-LISTEN-006
 * generalized: EVERY fallback path emits telemetry, enforced by construction.
 *
 * A `Degraded<T>` value cannot be fabricated: the brand is unexported, and the
 * only constructor lives in `@omi-core/kernel`, which requires a
 * `FallbackSink` to build one. Code that returns `T | Degraded<T>` therefore
 * cannot take a fallback path without the telemetry event existing first.
 * Do not weaken these types to route around the constructor — that is the
 * one thing this file exists to make impossible.
 */

declare const DegradedBrand: unique symbol;

/** A usable value produced by a fallback path, carrying its own evidence. */
export interface Degraded<T> {
  readonly value: T;
  readonly fallback: FallbackRecord;
  readonly [DegradedBrand]: true;
}

/** The telemetry event a fallback path must emit to exist. */
export interface FallbackRecord {
  /** Closed vocabulary per domain, e.g. "listen.decode.unknown-frame". */
  readonly path: string;
  /** What we fell back FROM and TO, for humans reading dashboards. */
  readonly from: string;
  readonly to: string;
  readonly detail?: string;
  readonly at: number;
}

export interface FallbackSink {
  record(event: FallbackRecord): void;
}

export type MaybeDegraded<T> = T | Degraded<T>;

export function isDegraded<T>(v: MaybeDegraded<T>): v is Degraded<T> {
  return typeof v === "object" && v !== null && "fallback" in (v as object) && "value" in (v as object);
}
