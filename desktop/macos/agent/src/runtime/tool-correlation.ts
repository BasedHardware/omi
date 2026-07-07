import type { QueryScopedOutbound } from "../protocol.js";

export interface ToolCallCorrelationInput {
  requestId?: string;
  clientId?: string;
  adapterId?: string;
}

export interface ToolCallCorrelationResolver {
  forRequest(requestId: string, clientId: string): Partial<QueryScopedOutbound>;
  forAdapter(adapterId: string): Partial<QueryScopedOutbound>;
  unscoped(): Partial<QueryScopedOutbound>;
}

export function resolveToolCallCorrelation(
  input: ToolCallCorrelationInput,
  resolver: ToolCallCorrelationResolver
): Partial<QueryScopedOutbound> {
  if (input.requestId) {
    if (!input.clientId) {
      return {};
    }
    const requestCorrelation = resolver.forRequest(input.requestId, input.clientId);
    return requestCorrelation.requestId ? requestCorrelation : {};
  }
  if (input.adapterId) {
    return resolver.forAdapter(input.adapterId);
  }
  return resolver.unscoped();
}
