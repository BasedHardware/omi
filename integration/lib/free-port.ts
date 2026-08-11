/** Reserve one loopback port for a test child, then release it before launch. */
export async function freeLoopbackPort(): Promise<number> {
  const probe = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    fetch: () => new Response(""),
  });
  const port = probe.port;
  await probe.stop(true);
  if (typeof port !== "number") throw new Error("expected numeric ephemeral port");
  return port;
}
