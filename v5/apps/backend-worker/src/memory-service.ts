import { parseSynthesizedPageJson } from "@omi-core/ratified-contracts/projections/synthesized";
import {
  requestCanonicalService,
  type CanonicalServiceRequest,
} from "./canonical-service";

export type CanonicalMemoryResult =
  | { kind: "page"; response: Response }
  | { kind: "denied"; status: 400 | 401 | 403 }
  | { kind: "unavailable" };

export async function readCanonicalMemoryPage(
  input: Omit<CanonicalServiceRequest, "path" | "method" | "body">
): Promise<CanonicalMemoryResult> {
  const result = await requestCanonicalService({
    ...input,
    path: "/v1/memories",
    method: "GET",
  });
  if (result.kind === "unavailable") return result;
  const bytes = await result.response.clone().arrayBuffer();
  const text = new TextDecoder("utf-8", {
    fatal: true,
    ignoreBOM: true,
  }).decode(bytes);
  if (result.response.status === 200) {
    return parseSynthesizedPageJson(text) === null
      ? { kind: "unavailable" }
      : { kind: "page", response: result.response };
  }
  const status = result.response.status;
  if (
    (status === 400 && text === '{"error":"bad_request"}') ||
    (status === 401 && text === '{"error":"unauthorized"}') ||
    (status === 403 && text === '{"error":"forbidden"}')
  ) {
    return { kind: "denied", status: status as 400 | 401 | 403 };
  }
  return { kind: "unavailable" };
}
