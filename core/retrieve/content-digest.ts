import { createHash } from "node:crypto";

const canonicalize = (value: unknown): string => {
  if (value === null) return "null";
  if (typeof value === "string" || typeof value === "boolean") return JSON.stringify(value);
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new TypeError("canonical content rejects non-finite numbers");
    return JSON.stringify(Object.is(value, -0) ? 0 : value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalize).join(",")}]`;
  if (typeof value === "object") {
    const entries = Object.entries(value).filter(([, item]) => item !== undefined).sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0);
    return `{${entries.map(([key, item]) => `${JSON.stringify(key)}:${canonicalize(item)}`).join(",")}}`;
  }
  throw new TypeError(`canonical content rejects ${typeof value}`);
};

/** Content identity only: callers retain the digest, never the unredacted canonical bytes. */
export const sha256CanonicalContent = (value: unknown): string =>
  createHash("sha256").update(canonicalize(value)).digest("hex");
