export type ChatMessage = {
  id: string;
  text: string;
  sender: "human" | "ai";
  createdAt: number;
  generationOutcome: "completed" | "cancelled" | null;
};

export type ChatCreate = {
  op: "create";
  opId: string;
  id: string;
  at: number;
  text: string;
  sender: "human";
  journalRevision: number;
  type?: "text" | "day_summary";
  appId?: null;
  chatSessionId?: null;
  messageSource?: string;
  metadata?: string | null;
  attachmentIds?: string[];
};

export type GenerationEvent = {
  id: string;
  kind: "accepted" | "done" | "failed" | "cancelled";
  message?: ChatMessage | null;
  error?: { code: string; retryable: boolean };
};

export const json = (
  value: unknown,
  status = 200,
  headers?: HeadersInit
): Response =>
  Response.json(value, {
    status,
    headers: { "cache-control": "no-store", ...headers },
  });

export const backendError = (
  code: string,
  action: string,
  status: number,
  retryable = false
): Response => json({ error: { code, retryable, action } }, status);

export const isChatCreate = (value: unknown): value is ChatCreate => {
  if (value === null || typeof value !== "object" || Array.isArray(value))
    return false;
  const item = value as Record<string, unknown>;
  return (
    item["op"] === "create" &&
    typeof item["opId"] === "string" &&
    item["opId"].length > 0 &&
    typeof item["id"] === "string" &&
    item["id"].length > 0 &&
    Number.isSafeInteger(item["at"]) &&
    (item["at"] as number) >= 0 &&
    typeof item["text"] === "string" &&
    item["text"].length > 0 &&
    item["sender"] === "human" &&
    Number.isSafeInteger(item["journalRevision"]) &&
    (item["journalRevision"] as number) >= 0 &&
    (item["appId"] === undefined || item["appId"] === null) &&
    (item["chatSessionId"] === undefined || item["chatSessionId"] === null) &&
    (item["attachmentIds"] === undefined ||
      (Array.isArray(item["attachmentIds"]) &&
        item["attachmentIds"].every(
          (id) => typeof id === "string" && id.length > 0
        )))
  );
};
