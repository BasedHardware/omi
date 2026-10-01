export type CanonicalService = {
  fetch(request: Request): Promise<Response>;
};

export type CanonicalCaller = {
  accountId: string;
  authorization: string | undefined;
  stagingApiToken: string;
};

export type CanonicalServiceRequest = {
  service: CanonicalService | undefined;
  caller: CanonicalCaller;
  path: "/v1/memories" | "/v1/tasks" | "/v1/tasks/ops";
  method: "GET" | "POST";
  query?: URLSearchParams;
  body?: string;
  contractVersion?: string;
};

export type CanonicalServiceResult =
  | { kind: "response"; response: Response }
  | { kind: "unavailable" };

export const MAX_CANONICAL_RESPONSE_BYTES = 6_000_000;

export async function requestCanonicalService(
  input: CanonicalServiceRequest
): Promise<CanonicalServiceResult> {
  const authorization = input.caller.authorization;
  const token = authorization?.startsWith("Bearer ")
    ? authorization.slice(7)
    : "";
  if (
    input.service === undefined ||
    !input.caller.accountId.startsWith("firebase:") ||
    input.caller.accountId.length <= "firebase:".length ||
    token.length === 0 ||
    token.length > 32_768 ||
    !["/v1/memories", "/v1/tasks", "/v1/tasks/ops"].includes(input.path) ||
    /[\s\x00-\x1f\x7f]/.test(token) ||
    token === input.caller.stagingApiToken ||
    (input.path === "/v1/tasks/ops") !== (input.method === "POST") ||
    (input.method === "GET" && input.body !== undefined) ||
    (input.body !== undefined && input.body.length > 1_000_000)
  ) {
    return { kind: "unavailable" };
  }
  const query = new URLSearchParams(input.query);
  if (
    [...query.keys()].some((key) => key !== "limit" && key !== "cursor") ||
    query.getAll("limit").length > 1 ||
    query.getAll("cursor").length > 1 ||
    (input.method === "POST" && query.size > 0)
  ) {
    return { kind: "unavailable" };
  }
  const headers = new Headers({
    authorization: `Bearer ${token}`,
    accept: "application/json",
  });
  if (input.body !== undefined) headers.set("content-type", "application/json");
  if (
    input.contractVersion !== undefined &&
    /^[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}$/.test(input.contractVersion)
  ) {
    headers.set("x-omi-contract-version", input.contractVersion);
  }
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const operation = async (): Promise<CanonicalServiceResult> => {
      const request = new Request(
        `https://canonical.omi.internal${input.path}${
          query.size > 0 ? `?${query}` : ""
        }`,
        {
          method: input.method,
          headers,
          ...(input.body === undefined ? {} : { body: input.body }),
          redirect: "manual",
          signal: controller.signal,
        }
      );
      const upstream = await input.service!.fetch(request);
      if (controller.signal.aborted) {
        await upstream.body?.cancel();
        return { kind: "unavailable" };
      }
      if (
        ![200, 201, 202, 204, 400, 401, 403, 409, 422, 429, 500, 503].includes(
          upstream.status
        ) ||
        (upstream.status !== 204 &&
          !/^application\/json(?:\s*;|$)/i.test(
            upstream.headers.get("content-type") ?? ""
          ))
      ) {
        await upstream.body?.cancel();
        return { kind: "unavailable" };
      }
      const bytes = await readBounded(upstream, controller.signal);
      if (bytes === null) return { kind: "unavailable" };
      const text = new TextDecoder("utf-8", {
        fatal: true,
        ignoreBOM: true,
      }).decode(bytes);
      if (text.startsWith("\uFEFF")) return { kind: "unavailable" };
      const responseHeaders = new Headers({
        "content-type": "application/json; charset=utf-8",
        "cache-control": "no-store",
      });
      const retryAfter = upstream.headers.get("retry-after");
      if (
        retryAfter !== null &&
        /^[0-9]+$/.test(retryAfter) &&
        Number(retryAfter) >= 1 &&
        Number(retryAfter) <= 3600
      ) {
        responseHeaders.set("retry-after", retryAfter);
      }
      return {
        kind: "response",
        response: new Response(upstream.status === 204 ? null : bytes, {
          status: upstream.status,
          headers: responseHeaders,
        }),
      };
    };
    return await Promise.race([
      operation(),
      new Promise<CanonicalServiceResult>((resolve) => {
        timer = setTimeout(() => {
          controller.abort();
          resolve({ kind: "unavailable" });
        }, 30_000);
      }),
    ]);
  } catch {
    return { kind: "unavailable" };
  } finally {
    clearTimeout(timer);
  }
}

async function readBounded(
  response: Response,
  signal: AbortSignal
): Promise<Uint8Array | null> {
  if (response.body === null) return new Uint8Array();
  if (signal.aborted) {
    await response.body.cancel();
    return null;
  }
  const reader = response.body.getReader();
  const abort = () => {
    void reader.cancel().catch(() => undefined);
  };
  signal.addEventListener("abort", abort, { once: true });
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (signal.aborted) return null;
      if (done) break;
      size += value.byteLength;
      if (size > MAX_CANONICAL_RESPONSE_BYTES) {
        await reader.cancel();
        return null;
      }
      chunks.push(value);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.byteLength;
    }
    return bytes;
  } finally {
    signal.removeEventListener("abort", abort);
    reader.releaseLock();
  }
}
