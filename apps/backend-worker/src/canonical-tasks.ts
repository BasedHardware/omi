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

export type CanonicalTasksRequest = {
  service: CanonicalService | undefined;
  caller: CanonicalCaller;
  contractVersion?: string;
} & (
  | { method: "GET"; query: URLSearchParams }
  | { method: "POST"; body: string }
);

export type CanonicalWritePath = "/v1/tasks/ops" | "/v1/stm-notes/ops";

export type CanonicalWriteRequest = {
  service: CanonicalService | undefined;
  caller: CanonicalCaller;
  path: CanonicalWritePath;
  body: string;
  requireAcknowledgedRecordMatch?: boolean;
  contractVersion?: string;
};

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
  if (request.method === "POST") {
    return requestCanonicalWrite({
      service: request.service,
      caller: request.caller,
      path: "/v1/tasks/ops",
      body: request.body,
      ...(request.contractVersion === undefined
        ? {}
        : { contractVersion: request.contractVersion }),
    });
  }
  const result = await requestCanonicalService({
    service: request.service,
    caller: request.caller,
    path: "/v1/tasks",
    method: "GET",
    query: request.query,
    ...(request.contractVersion === undefined
      ? {}
      : { contractVersion: request.contractVersion }),
  });
  if (result.kind === "unavailable") return canonicalTasksUnavailable("GET");
  const response = result.response;
  const body = await response.text();
  const valid =
    response.status === 200
      ? parseTaskPageJson(body) !== null
      : [
          [400, '{"error":"bad_request"}'],
          [401, '{"error":"unauthorized"}'],
          [403, '{"error":"forbidden"}'],
        ].some(
          ([status, value]) => response.status === status && body === value
        );
  return valid
    ? new Response(body, { status: response.status, headers: response.headers })
    : canonicalTasksUnavailable("GET");
}

export async function requestCanonicalWrite(
  request: CanonicalWriteRequest
): Promise<Response> {
  const result = await requestCanonicalService({
    service: request.service,
    caller: request.caller,
    path: request.path,
    method: "POST",
    body: request.body,
    ...(request.contractVersion === undefined
      ? {}
      : { contractVersion: request.contractVersion }),
  });
  if (result.kind === "unavailable") return canonicalTasksUnavailable("POST");
  const response = result.response;
  const body = await response.text();
  let valid = false;
  if (response.status === 200) {
    try {
      const accepted: unknown = JSON.parse(body);
      valid =
        isTrustedWriteAccepted(accepted) &&
        (!request.requireAcknowledgedRecordMatch ||
          accepted.applied.record_id === requestedRecordId(request.body));
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
    : canonicalTasksUnavailable("POST");
}

function requestedRecordId(body: string): string | null {
  try {
    const envelope: unknown = JSON.parse(body);
    if (
      envelope === null ||
      typeof envelope !== "object" ||
      Array.isArray(envelope)
    ) {
      return null;
    }
    const op = (envelope as Record<string, unknown>)["op"];
    if (op === null || typeof op !== "object" || Array.isArray(op)) {
      return null;
    }
    const recordId = (op as Record<string, unknown>)["record_id"];
    return typeof recordId === "string" ? recordId : null;
  } catch {
    return null;
  }
}
