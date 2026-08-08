#!/usr/bin/env node
// Dependency-free dev server: serves surface/, strips TS types on the fly
// (node:module.stripTypeScriptTypes, Node >= 22.13), live-reloads via SSE + fs.watch.
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { watch } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join, extname, normalize } from "node:path";

const root = dirname(fileURLToPath(import.meta.url));
const port = Number(process.env.OMI_SURFACE_PORT ?? 5290);
const MIME = { ".html": "text/html", ".js": "text/javascript", ".ts": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml" };

const clients = new Set();
const LIVE_RELOAD = `<script>new EventSource("/__live").onmessage=e=>{if(e.data==="reload")location.reload()}</script>`;

const server = createServer(async (req, res) => {
  const url = new URL(req.url, "http://127.0.0.1");
  if (url.pathname === "/__live") {
    res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache", connection: "keep-alive" });
    res.write("retry: 250\n\n");
    clients.add(res);
    req.on("close", () => clients.delete(res));
    return;
  }
  if (url.pathname === "/__selftest" && req.method === "POST") {
    const chunks = [];
    for await (const c of req) chunks.push(c);
    console.log(`[selftest] ${Buffer.concat(chunks).toString()}`);
    res.writeHead(204).end();
    return;
  }
  let rel = normalize(decodeURIComponent(url.pathname)).replace(/^(\.\.[/\\])+/, "");
  if (rel === "/" || rel === "\\") rel = "/index.html";
  const path = join(root, rel);
  try {
    if (!(await stat(path)).isFile()) throw new Error("not a file");
    const ext = extname(path);
    let body = await readFile(path, "utf8");
    if (ext === ".ts") body = stripTypeScriptTypes(body, { mode: "strip" });
    if (ext === ".html") body = body.replace("</body>", `${LIVE_RELOAD}</body>`);
    res.writeHead(200, { "content-type": `${MIME[ext] ?? "application/octet-stream"}; charset=utf-8`, "cache-control": "no-store" });
    res.end(body);
    if (process.env.OMI_TRACE) console.log(`[req] ${Date.now()} ${rel}`);
  } catch (err) {
    const ts = err?.message?.includes("Unexpected") || err?.name === "SyntaxError";
    res.writeHead(ts ? 500 : 404, { "content-type": "text/plain" });
    res.end(ts ? `type-strip failed: ${err.message}` : "404");
  }
});

let timer;
watch(root, { recursive: true }, (_e, file) => {
  if (file?.includes("node_modules") || file?.startsWith(".")) return;
  clearTimeout(timer);
  timer = setTimeout(() => {
    for (const c of clients) c.write("data: reload\n\n");
    console.log(`[reload] ${Date.now()} ${file} -> ${clients.size} client(s)`);
  }, 25);
});

server.listen(port, "127.0.0.1", () => console.log(`surface dev server: http://127.0.0.1:${port}/`));
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => { server.close(); process.exit(0); });
