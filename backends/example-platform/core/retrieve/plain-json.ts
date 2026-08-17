import { isProxy } from "node:util/types";

const arrayIndex = /^(0|[1-9]\d*)$/;

const copyPlainJson = (value: unknown, active: WeakSet<object>): unknown => {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new TypeError("plain JSON rejects non-finite numbers");
    return Object.is(value, -0) ? 0 : value;
  }
  if (typeof value !== "object") throw new TypeError(`plain JSON rejects ${typeof value}`);
  if (isProxy(value)) throw new TypeError("plain JSON rejects proxies");
  if (active.has(value)) throw new TypeError("plain JSON rejects cycles");
  active.add(value);

  const isArray = Array.isArray(value);
  const prototype = Object.getPrototypeOf(value);
  if (isArray ? prototype !== Array.prototype : prototype !== Object.prototype && prototype !== null) {
    throw new TypeError("plain JSON rejects non-plain prototypes");
  }
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => typeof key === "symbol")) throw new TypeError("plain JSON rejects symbol keys");
  if (isArray) {
    const strings = keys as string[];
    if (strings.length !== value.length + 1
      || strings.some((key) => key !== "length" && (!arrayIndex.test(key) || Number(key) >= value.length))) {
      throw new TypeError("plain JSON rejects array properties");
    }
    for (let index = 0; index < value.length; index++) if (!Object.prototype.hasOwnProperty.call(value, String(index))) {
      throw new TypeError("plain JSON rejects sparse arrays");
    }
  }
  const dataKeys = (keys as string[]).filter((key) => !isArray || key !== "length").sort();
  const output: unknown[] | Record<string, unknown> = isArray ? [] : {};
  for (const key of dataKeys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) throw new TypeError("plain JSON requires enumerable own data properties");
    const copied = copyPlainJson(descriptor.value, active);
    if (isArray) output[Number(key)] = copied;
    // Define, never assign. A null-prototype source can legitimately carry
    // `__proto__` as an ordinary own key (drivers build records with
    // `Object.create(null)`), and plain assignment would invoke the inherited
    // `__proto__` setter on the destination: the field would silently vanish
    // from the copy AND the copy's prototype would be replaced by attacker-
    // supplied data. `Object.defineProperty` makes it an own data property like
    // any other, so the exact-shape validators downstream can reject it
    // explicitly instead of never seeing it.
    else Object.defineProperty(output, key, {
      value: copied, enumerable: true, writable: true, configurable: true,
    });
  }
  active.delete(value);
  return output;
};

/** Canonical plain-data tree: sorted record keys and no shared-reference aliases. */
export const normalizePlainJson = <Value>(value: Value): Value => copyPlainJson(value, new WeakSet()) as Value;

export const deepFreezePlainJson = <Value>(value: Value): Value => {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    for (const nested of Object.values(value)) deepFreezePlainJson(nested);
    Object.freeze(value);
  }
  return value;
};
