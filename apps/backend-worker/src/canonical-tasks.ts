import { parseTaskPageJson } from "@omi-core/ratified-contracts/projections/tasks";
import {
  isTrustedWriteAccepted,
  WRITE_AVAILABILITY,
  WRITE_ERRORS,
  WRITE_REFUSALS,
} from "@omi-core/ratified-contracts/write/ops";
import {
  requestCanonicalService,
  type CanonicalCaller,
  type CanonicalService,
} from "./canonical-service";
import { backendError } from "./wire";

export type CanonicalTasksRequest = {
  service: CanonicalService | undefined;
  caller: CanonicalCaller;
  contractVersion?: string;
} & (
  | { method: "GET"; query: URLSearchParams }
  | { method: "POST"; body: string }
);

export function canonicalTasksUnavailable(method: "GET" | "POST"): Response {
  const unavailable = WRITE_AVAILABILITY.control_unavailable;
  return new Response(
    method === "POST" ? unavailable.body : '{"error":"internal_server_error"}',
    {
      status: 503,
      headers: {
        "content-type": "application/json",
        "cache-control": "no-store",
        "retry-after": String(unavailable.retryAfterSeconds),
      },
    }
  );
}

export async function requestCanonicalTasks(
  request: CanonicalTasksRequest
): Promise<Response> {
  const result = await requestCanonicalService({
    service: request.service,
    caller: request.caller,
    path: request.method === "GET" ? "/v1/tasks" : "/v1/tasks/ops",
    method: request.method,
    ...(request.method === "GET"
      ? { query: request.query }
      : { body: request.body }),
    ...(request.contractVersion === undefined
      ? {}
      : { contractVersion: request.contractVersion }),
  });
  if (result.kind === "unavailable")
    return canonicalTasksUnavailable(request.method);
  const response = result.response;
  const body = await response.text();
  let valid = false;
  if (request.method === "GET") {
    if (response.status === 200) {
      return parseTaskPageJson(body) === null
        ? backendError("projection_unavailable", "none", 503)
        : new Response(body, {
            status: response.status,
            headers: response.headers,
          });
    }
    valid = [
      [400, '{"error":"bad_request"}'],
      [401, '{"error":"unauthorized"}'],
      [403, '{"error":"forbidden"}'],
    ].some(([status, value]) => response.status === status && body === value);
  } else if (response.status === 200) {
    try {
      valid = isTrustedWriteAccepted(JSON.parse(body));
    } catch {
      valid = false;
    }
  } else {
    valid = [
      ...Object.values(WRITE_REFUSALS),
      ...Object.values(WRITE_ERRORS),
      WRITE_AVAILABILITY.control_unavailable,
    ].some((value) => response.status === value.status && body === value.body);
  }
  return valid
    ? new Response(body, { status: response.status, headers: response.headers })
    : canonicalTasksUnavailable(request.method);
}
