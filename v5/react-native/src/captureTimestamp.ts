export function isOptionalCaptureTimestamp(
  value: unknown,
): value is number | undefined {
  return (
    value === undefined ||
    (typeof value === 'number' &&
      Number.isSafeInteger(value) &&
      value >= 0 &&
      value <= 8_640_000_000_000_000)
  );
}
