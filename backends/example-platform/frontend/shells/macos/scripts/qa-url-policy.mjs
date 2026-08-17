#!/usr/bin/env node
// LIFECYCLE: permanent

// Canonicalizes the two network authorities accepted by dev-run-macos.sh.
// Errors are deliberately generic: an invalid URL may contain credentials and
// must never be reflected into launcher output.

const [kind, raw] = process.argv.slice(2);

function refuse() {
  process.stderr.write("invalid or forbidden QA URL\n");
  process.exit(1);
}

if ((kind !== "api" && kind !== "issuer") || typeof raw !== "string" || raw.length === 0 || raw.trim() !== raw) {
  refuse();
}

let url;
try {
  url = new URL(raw);
} catch {
  refuse();
}

if (url.protocol !== "http:" && url.protocol !== "https:") refuse();
const hostname = url.hostname.toLowerCase().replace(/\.+$/, "");
if (hostname.length === 0 || hostname === "api.omi.me") refuse();
if (url.username !== "" || url.password !== "" || url.hash !== "") refuse();

url.hostname = hostname;
if (kind === "api") {
  if ((url.pathname !== "" && url.pathname !== "/") || url.search !== "") refuse();
  process.stdout.write(url.origin);
} else {
  process.stdout.write(url.toString());
}
