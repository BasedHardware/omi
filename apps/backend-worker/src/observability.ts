export const OBSERVABILITY_SINK_MODES = [
  "cloudflare_only",
  "better_stack",
] as const;

export type ObservabilitySinkMode = (typeof OBSERVABILITY_SINK_MODES)[number];

export type ObservabilityEnv = {
  OBSERVABILITY_SINK_MODE: string | undefined;
};

export function parseObservabilitySinkMode(
  value: string | undefined
): ObservabilitySinkMode | null {
  return OBSERVABILITY_SINK_MODES.includes(value as ObservabilitySinkMode)
    ? (value as ObservabilitySinkMode)
    : null;
}

export function observabilityConfigured(env: ObservabilityEnv): boolean {
  return parseObservabilitySinkMode(env.OBSERVABILITY_SINK_MODE) !== null;
}

export function requestCompletedEvent(input: {
  requestId: string;
  method: string;
  route: string;
  status: number;
  durationMs: number;
}) {
  return {
    event: "request_completed",
    request_id: input.requestId,
    correlation_id: input.requestId,
    method: input.method,
    route: input.route,
    status: input.status,
    duration_ms: input.durationMs,
  };
}

export function configurationNotReadyEvent(input: {
  requestId: string;
  route: string;
}) {
  return {
    event: "configuration_not_ready",
    request_id: input.requestId,
    route: input.route,
  };
}

export function generationAdmittedEvent(input: {
  requestId: string;
  generationId: string;
}) {
  return {
    event: "generation_admitted",
    request_id: input.requestId,
    correlation_id: input.generationId,
  };
}

export function requestFailedEvent(input: {
  requestId: string;
  name: string;
  route: string;
}) {
  return {
    event: "request_failed",
    request_id: input.requestId,
    name: input.name,
    route: input.route,
  };
}

export function logRequestCompleted(input: {
  requestId: string;
  method: string;
  route: string;
  status: number;
  durationMs: number;
}): void {
  console.log(JSON.stringify(requestCompletedEvent(input)));
}

export function logRequestFailed(input: {
  requestId: string;
  name: string;
  route: string;
}): void {
  console.error(JSON.stringify(requestFailedEvent(input)));
}

export function gatewayFailureEvent(input: {
  message: string;
  correlationId: string;
  model: string;
  status: number;
}) {
  return {
    event: "ai_gateway_failed",
    message: input.message,
    correlation_id: input.correlationId,
    model: input.model,
    status: input.status,
  };
}
