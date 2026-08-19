export const LOCAL_PROXY_PREFIX = "/__omi/api";

const forbiddenHeaders = new Set([
  "authorization",
  "cookie",
  "proxy-authorization",
]);

function isLoopbackHostname(hostname: string): boolean {
  const normalized = hostname.replace(/^\[|\]$/g, "").toLocaleLowerCase();
  return (
    normalized === "localhost" ||
    normalized === "127.0.0.1" ||
    normalized === "::1"
  );
}

export function assertLoopbackBackendUrl(value: string): URL {
  const url = new URL(value);
  if (
    (url.protocol !== "http:" && url.protocol !== "https:") ||
    !isLoopbackHostname(url.hostname) ||
    url.username !== "" ||
    url.password !== "" ||
    url.pathname !== "/" ||
    url.search !== "" ||
    url.hash !== ""
  ) {
    throw new Error(
      "OMI_LOCAL_BACKEND_URL must be a loopback origin without credentials"
    );
  }
  return url;
}

export function assertLocalProxyPath(path: string): string {
  if (!path.startsWith("/") || path.startsWith("//")) {
    throw new Error("local proxy paths must be origin-relative");
  }
  const url = new URL(path, "http://omi.local");
  if (
    url.origin !== "http://omi.local" ||
    (url.pathname !== LOCAL_PROXY_PREFIX &&
      !url.pathname.startsWith(`${LOCAL_PROXY_PREFIX}/`))
  ) {
    throw new Error("local proxy paths must stay under the local API prefix");
  }
  return `${url.pathname}${url.search}`;
}

export function rewriteLocalProxyPath(path: string): string {
  const safePath = assertLocalProxyPath(path);
  const rewritten = safePath.slice(LOCAL_PROXY_PREFIX.length);
  return rewritten === "" ? "/" : rewritten;
}

export function localProxyRequestInit(init: RequestInit = {}): RequestInit {
  const headers = new Headers(init.headers);
  headers.forEach((_value, name) => {
    if (forbiddenHeaders.has(name.toLocaleLowerCase())) {
      throw new Error(`browser requests cannot set ${name}`);
    }
  });
  return { ...init, headers };
}
