// Transport adapter for rx4-smoke: rx4 streams OpenAI SSE, but some
// OpenAI-compatible endpoints (for example the Z.ai coding-plan endpoint)
// only answer non-streaming JSON. This shim forwards /v1/chat/completions
// upstream without streaming and re-emits the completion as standard chunk
// events plus [DONE], so rx4's SSE parser sees a well-formed stream.
//
//   UPSTREAM_URL   full chat/completions URL of the real endpoint (required)
//   SHIM_PORT      local port to listen on (default 8787)
//
// The caller's Authorization header is forwarded unchanged; no key is read,
// logged, or stored here.

const UPSTREAM_URL = Bun.env.UPSTREAM_URL;
if (!UPSTREAM_URL) throw new Error("set UPSTREAM_URL to the real chat/completions URL");
const PORT = Number(Bun.env.SHIM_PORT ?? 8787);

function chunk(id, model, delta, finish, usage) {
  const out = {
    id,
    object: "chat.completion.chunk",
    created: Math.floor(Date.now() / 1000),
    model,
    choices: [{ index: 0, delta, finish_reason: finish }],
  };
  if (usage) out.usage = usage;
  return out;
}

Bun.serve({
  port: PORT,
  async fetch(req) {
    const url = new URL(req.url);
    if (!url.pathname.endsWith("/chat/completions")) {
      return new Response("not found", { status: 404 });
    }
    const body = await req.json();
    delete body.stream;
    delete body.stream_options;
    const upstream = await fetch(UPSTREAM_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: req.headers.get("authorization") ?? "",
      },
      body: JSON.stringify(body),
    });
    if (!upstream.ok) {
      return new Response(await upstream.text(), { status: upstream.status });
    }
    const json = await upstream.json();
    const msg = json.choices?.[0]?.message ?? {};
    const id = json.id ?? "shim";
    const model = json.model ?? body.model;
    const enc = new TextEncoder();
    const sse = (obj) => enc.encode(`data: ${JSON.stringify(obj)}\n\n`);

    const delta = { role: "assistant" };
    if (typeof msg.content === "string" && msg.content.length > 0) {
      delta.content = msg.content;
    }
    const toolCalls = Array.isArray(msg.tool_calls) ? msg.tool_calls : [];
    if (toolCalls.length > 0) {
      delta.tool_calls = toolCalls.map((tc, i) => ({
        index: i,
        id: tc.id,
        type: "function",
        function: { name: tc.function?.name, arguments: tc.function?.arguments ?? "{}" },
      }));
    }
    const finish = toolCalls.length > 0 ? "tool_calls" : "stop";

    const stream = new ReadableStream({
      start(c) {
        c.enqueue(sse(chunk(id, model, delta, null)));
        c.enqueue(sse(chunk(id, model, {}, finish, json.usage)));
        c.enqueue(enc.encode("data: [DONE]\n\n"));
        c.close();
      },
    });
    return new Response(stream, {
      headers: { "Content-Type": "text/event-stream" },
    });
  },
});
console.log(`sse-shim listening on 127.0.0.1:${PORT} -> ${UPSTREAM_URL}`);
