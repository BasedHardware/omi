/**
 * Parses bounded canonical JSON text before applying a contract validator.
 *
 * Canonical input is exactly `JSON.stringify(JSON.parse(raw))`: compact encoding,
 * normalized escapes/numbers, preserved object-key order, and no duplicate keys.
 * The round trip makes duplicate-key payloads fail because JSON.parse retains only
 * the last value. JSON.parse creates data-only objects and executes no caller code.
 */
export function parseCanonicalJson<T>(
  raw: string,
  maxCodeUnits: number,
  predicate: (value: unknown) => value is T,
): T | null {
  if (typeof raw !== "string" || raw.length === 0 || raw.length > maxCodeUnits) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (JSON.stringify(parsed) !== raw) return null;
    return predicate(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

/**
 * Accepts only a deep graph shaped exactly like mutable JSON.parse output.
 *
 * Descriptor inspection rejects ordinary accessors without invoking getters,
 * plus symbols, non-enumerable/readonly properties, holes, extra array keys,
 * class instances, cycles, and non-finite numbers. structuredClone is then used
 * to reject Proxy objects anywhere in the graph. ECMAScript offers no trap-free
 * Proxy inspection; a hostile Proxy may execute traps during descriptor checks,
 * so callers must use parseCanonicalJson for untrusted input.
 */
export function isPlainJsonDataGraph(value: unknown): boolean {
  try {
    if (!inspectData(value, new Set<object>())) return false;
    const clone = (globalThis as { structuredClone?: (input: unknown) => unknown }).structuredClone;
    if (typeof clone !== "function") return false;
    clone(value);
    return true;
  } catch {
    return false;
  }
}

function inspectData(value: unknown, seen: Set<object>): boolean {
  if (value === null || typeof value === "string" || typeof value === "boolean") return true;
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value !== "object" || seen.has(value)) return false;
  seen.add(value);

  if (Array.isArray(value)) return inspectArray(value, seen);
  if (Object.getPrototypeOf(value) !== Object.prototype) return false;

  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => typeof key === "symbol")) return false;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  for (const key of keys as string[]) {
    const descriptor = descriptors[key];
    if (!isJsonDataDescriptor(descriptor) || !inspectData(descriptor.value, seen)) return false;
  }
  return true;
}

function inspectArray(value: unknown[], seen: Set<object>): boolean {
  if (Object.getPrototypeOf(value) !== Array.prototype) return false;
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => typeof key === "symbol")) return false;
  const expected = Array.from({ length: value.length }, (_, index) => String(index));
  expected.push("length");
  if (keys.length !== expected.length || !expected.every((key) => keys.includes(key))) return false;

  const descriptors = Object.getOwnPropertyDescriptors(value);
  const lengthDescriptor = Object.getOwnPropertyDescriptor(value, "length");
  if (!lengthDescriptor || "get" in lengthDescriptor || lengthDescriptor.enumerable || lengthDescriptor.configurable || !lengthDescriptor.writable) return false;
  for (const key of expected.slice(0, -1)) {
    const descriptor = descriptors[key];
    if (!isJsonDataDescriptor(descriptor) || !inspectData(descriptor.value, seen)) return false;
  }
  return true;
}

function isJsonDataDescriptor(
  descriptor: PropertyDescriptor | undefined,
): descriptor is PropertyDescriptor & { value: unknown } {
  return Boolean(
    descriptor
      && !("get" in descriptor)
      && descriptor.enumerable
      && descriptor.configurable
      && descriptor.writable,
  );
}
