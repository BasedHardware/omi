export const ADMIN_LLM_LANES = {
  chatLab: "omi:auto:persona-chat-premium",
  notificationRegeneration: "omi:auto:proactive-notification",
} as const;

type GatewayMessage = {
  role: "system" | "user" | "assistant";
  content: string;
};

type GatewayRequest = {
  lane: (typeof ADMIN_LLM_LANES)[keyof typeof ADMIN_LLM_LANES];
  feature: string;
  messages: GatewayMessage[];
  responseFormat?: Record<string, unknown>;
  temperature?: number;
};

export class AdminLlmGatewayUnavailableError extends Error {
  constructor() {
    super("The LLM gateway is unavailable");
    this.name = "AdminLlmGatewayUnavailableError";
  }
}

export async function invokeAdminLlmGateway(
  request: GatewayRequest,
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  const gatewayUrl = process.env.OMI_LLM_GATEWAY_URL?.trim();
  const gatewayToken = process.env.OMI_LLM_GATEWAY_SERVICE_TOKEN?.trim();
  if (!gatewayUrl || !gatewayToken) throw new AdminLlmGatewayUnavailableError();

  let response: Response;
  try {
    response = await fetchImpl(
      `${gatewayUrl.replace(/\/+$/, "")}/v1/chat/completions`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${gatewayToken}`,
          "Content-Type": "application/json",
          "X-Omi-Service-Caller": "omi-admin-dashboard",
          "X-Omi-LLM-Feature": request.feature,
        },
        body: JSON.stringify({
          model: request.lane,
          messages: request.messages,
          ...(request.responseFormat
            ? { response_format: request.responseFormat }
            : {}),
          temperature: request.temperature ?? 0.3,
        }),
      },
    );
  } catch {
    throw new AdminLlmGatewayUnavailableError();
  }

  if (!response.ok) throw new AdminLlmGatewayUnavailableError();
  const payload = (await response.json()) as {
    choices?: Array<{ message?: { content?: unknown } }>;
  };
  const content = payload.choices?.[0]?.message?.content;
  if (typeof content !== "string" || !content.trim())
    throw new AdminLlmGatewayUnavailableError();
  return content;
}
