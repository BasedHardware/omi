/** Only controlled descriptions may reach cards/logs; upstream bodies can contain secrets. */
export class WallSourceError extends Error {
  constructor(message: string, readonly retryable = false) {
    super(message);
    this.name = "WallSourceError";
  }
}
export function wallFailure(source: string, error: unknown): string {
  if (error instanceof WallSourceError) return error.message;
  if (
    error instanceof Error &&
    ["TimeoutError", "AbortError"].includes(error.name)
  )
    return `${source} request timed out`;
  return `${source} request failed; check source connectivity/configuration`;
}
