export type ReadyResult =
  | { kind: "ready"; environment: string }
  | { kind: "error"; reason: string };

export function sanitizeDisplayUrl(input: string): string {
  try {
    const parsed = new URL(input);
    parsed.username = "";
    parsed.password = "";
    parsed.search = "";
    parsed.hash = "";
    return parsed.toString();
  } catch {
    return "[invalid]";
  }
}

export async function verifyReady(url: string): Promise<ReadyResult> {
  let response: Response;
  try {
    response = await fetch(url, {
      headers: { accept: "application/json" },
      redirect: "manual",
    });
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    return { kind: "error", reason: `fetch failed: ${reason}` };
  }

  if (response.status !== 200) {
    return { kind: "error", reason: `unexpected status ${response.status}` };
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return { kind: "error", reason: "content-type is not application/json" };
  }

  const cacheControl = response.headers.get("cache-control") ?? "";
  if (!cacheControl.includes("no-store")) {
    return { kind: "error", reason: "cache-control is missing no-store" };
  }

  let body: unknown;
  try {
    body = (await response.json()) as unknown;
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    return { kind: "error", reason: `json parse failed: ${reason}` };
  }

  const record =
    typeof body === "object" && body !== null
      ? (body as Record<string, unknown>)
      : null;
  if (
    record === null ||
    record["status"] !== "ready" ||
    typeof record["environment"] !== "string" ||
    record["environment"] === ""
  ) {
    return { kind: "error", reason: "invalid /ready envelope" };
  }

  return { kind: "ready", environment: record["environment"] };
}

export async function main(args: string[]): Promise<number> {
  const url = args[0];
  if (url === undefined || url.length === 0) {
    console.error("usage: verify-ready <url>");
    return 1;
  }

  const result = await verifyReady(url);
  if (result.kind === "ready") {
    console.log(`ready: ${result.environment}`);
    return 0;
  }

  console.error(`not ready: ${result.reason} at ${sanitizeDisplayUrl(url)}`);
  return 1;
}

if (import.meta.main) {
  main(Bun.argv.slice(2))
    .then((code) => process.exit(code))
    .catch(() => process.exit(1));
}
