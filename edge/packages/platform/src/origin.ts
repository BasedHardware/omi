/** Reverse-proxy helper — any runtime with fetch. */

export type ProxyOptions = {
  originBase: string;
  request: Request;
  /** Extra request headers (overwrite). */
  headers?: Record<string, string>;
  edgeName?: string;
};

export async function proxyToOrigin(opts: ProxyOptions): Promise<Response> {
  const base = opts.originBase.replace(/\/$/, "");
  if (!base) {
    return Response.json({ error: "ORIGIN_API_BASE unset" }, { status: 500 });
  }
  const url = new URL(opts.request.url);
  const target = `${base}${url.pathname}${url.search}`;

  const headers = new Headers(opts.request.headers);
  headers.delete("host");
  headers.set("x-forwarded-host", url.host);
  headers.set("x-omi-edge", opts.edgeName || "gateway");
  if (opts.headers) {
    for (const [k, v] of Object.entries(opts.headers)) headers.set(k, v);
  }

  const init: RequestInit = {
    method: opts.request.method,
    headers,
    redirect: "manual",
  };
  if (opts.request.method !== "GET" && opts.request.method !== "HEAD") {
    init.body = opts.request.body;
    // @ts-expect-error duplex for streaming body on some runtimes
    init.duplex = "half";
  }

  const res = await fetch(target, init);
  const outHeaders = new Headers(res.headers);
  outHeaders.set("x-omi-edge", opts.edgeName || "gateway");
  return new Response(res.body, { status: res.status, headers: outHeaders });
}
