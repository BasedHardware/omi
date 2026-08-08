/**
 * Parses bounded canonical JSON text before applying a contract validator.
 *
 * Canonical input is the compact JSON.stringify encoding of JSON.parse(raw), with
 * object-key order preserved. Before serialization, the parsed data is copied by
 * descriptor into a graph whose objects and arrays have null prototypes. This keeps
 * canonical verification from consulting inherited getters such as toJSON. The
 * round trip rejects normalized escapes/numbers and duplicate-key payloads because
 * JSON.parse retains only the last duplicate. No caller-owned code is executed.
 */
export function parseCanonicalJson<T>(
  raw: string,
  maxCodeUnits: number,
  predicate: (value: unknown) => value is T,
): T | null {
  if (typeof raw !== "string" || raw.length === 0 || raw.length > maxCodeUnits) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (JSON.stringify(detachJsonData(parsed)) !== raw) return null;
    return predicate(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

/** Copies JSON.parse output without reading a property through its prototype. */
function detachJsonData(value: unknown): unknown {
  if (value === null || typeof value !== "object") return value;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (Array.isArray(value)) {
    const length = descriptors["length"]?.value;
    if (!Number.isSafeInteger(length) || length < 0) throw new TypeError("invalid JSON array length");
    const detached: unknown[] = [];
    Object.setPrototypeOf(detached, null);
    for (let index = 0; index < length; index += 1) {
      const key = String(index);
      const descriptor = descriptors[key];
      if (!isJsonDataDescriptor(descriptor)) throw new TypeError("invalid JSON array entry");
      Object.defineProperty(detached, key, { ...descriptor, value: detachJsonData(descriptor.value) });
    }
    return detached;
  }

  const detached = Object.create(null) as Record<string, unknown>;
  for (const key of Reflect.ownKeys(value)) {
    if (typeof key !== "string") throw new TypeError("invalid JSON object key");
    const descriptor = descriptors[key];
    if (!isJsonDataDescriptor(descriptor)) throw new TypeError("invalid JSON object property");
    Object.defineProperty(detached, key, { ...descriptor, value: detachJsonData(descriptor.value) });
  }
  return detached;
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
  if (!lengthDescriptor || Object.hasOwn(lengthDescriptor, "get") || lengthDescriptor.enumerable || lengthDescriptor.configurable || !lengthDescriptor.writable) return false;
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
      && Object.hasOwn(descriptor, "value")
      && descriptor.enumerable
      && descriptor.configurable
      && descriptor.writable,
  );
}
