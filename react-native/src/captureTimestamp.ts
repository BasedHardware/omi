export function isCaptureTimestamp(value: unknown): value is number {
  return (
    typeof value === 'number' &&
    Number.isSafeInteger(value) &&
    value >= 0 &&
    value <= 8_640_000_000_000_000
  );
}

export function isOptionalCaptureTimestamp(
  value: unknown,
): value is number | undefined {
  return value === undefined || isCaptureTimestamp(value);
}
