import {
  createHash,
  createPrivateKey,
  createPublicKey,
  sign,
} from "node:crypto";
import { GoogleAuth } from "google-auth-library";

const ORIGIN = "https://monitor.omi.me";
const ISSUER = "https://admin.omi.me";
const TTL = 240;
let auth: GoogleAuth | undefined;
const cache = new Map<string, { until: number; value: Record<string, any> }>();

export function embedEnabled(): boolean {
  return process.env.GRAFANA_EMBED_ENABLED === "true";
}

async function secret(
  resource: string | undefined
): Promise<Record<string, any>> {
  if (
    !resource ||
    !/^projects\/[\w-]+\/secrets\/[\w-]+\/versions\/\d+$/.test(resource)
  ) {
    throw new Error("Grafana secret version is not configured");
  }
  const prior = cache.get(resource);
  if (prior && prior.until > Date.now()) return prior.value;
  auth ??= new GoogleAuth({
    scopes: ["https://www.googleapis.com/auth/cloud-platform"],
  });
  const access = await auth.getAccessToken();
  if (!access) throw new Error("Grafana secret access unavailable");
  const response = await fetch(
    `https://secretmanager.googleapis.com/v1/${resource}:access`,
    {
      headers: { Authorization: `Bearer ${access}` },
      signal: AbortSignal.timeout(10_000),
      cache: "no-store",
    }
  );
  if (!response.ok) throw new Error("Grafana secret access unavailable");
  const envelope = await response.json();
  const value = JSON.parse(
    Buffer.from(envelope.payload.data, "base64").toString("utf8")
  );
  cache.set(resource, { value, until: Date.now() + 60_000 });
  return value;
}

async function signingKey() {
  const config = await secret(process.env.GRAFANA_EMBED_SIGNING_SECRET);
  if (typeof config.kid !== "string" || !/^[\w-]{1,80}$/.test(config.kid)) {
    throw new Error("Invalid Grafana signing key ID");
  }
  const key = createPrivateKey(config.privateKeyPem);
  if (
    key.asymmetricKeyType !== "rsa" ||
    (key.asymmetricKeyDetails?.modulusLength ?? 0) < 2048
  ) {
    throw new Error("Invalid Grafana signing key");
  }
  return { key, kid: config.kid };
}

export async function embedJwks() {
  const { key, kid } = await signingKey();
  const jwk = createPublicKey(key).export({ format: "jwk" });
  return { keys: [{ ...jwk, kid, alg: "RS256", use: "sig" }] };
}

async function grafana(
  path: string,
  bearer: string,
  body?: object,
  jwt = false
) {
  const response = await fetch(ORIGIN + path, {
    method: body ? "POST" : "GET",
    headers: {
      [jwt ? "X-Omi-Grafana-JWT" : "Authorization"]: jwt
        ? bearer
        : `Bearer ${bearer}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
    redirect: "error",
    cache: "no-store",
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) throw new Error("Grafana enrollment unavailable");
  return response.json();
}

export async function mintEmbed(uid: string) {
  const { key, kid } = await signingKey();
  const membership = await secret(process.env.GRAFANA_BUSINESS_TOKEN_SECRET);
  if (
    membership.orgId !== 2 ||
    !Number.isSafeInteger(membership.teamId) ||
    membership.teamId <= 0 ||
    !membership.token
  ) {
    throw new Error("Invalid Grafana Business configuration");
  }
  const login = `omi-business:${createHash("sha256")
    .update(uid)
    .digest("hex")}`;
  const now = Math.floor(Date.now() / 1000);
  const encode = (value: object) =>
    Buffer.from(JSON.stringify(value)).toString("base64url");
  const unsigned = `${encode({ alg: "RS256", typ: "JWT", kid })}.${encode({
    sub: login,
    email: `${login.slice(13)}@grafana-business.omi.me`,
    iss: ISSUER,
    aud: ORIGIN,
    purpose: "omi-business-embed",
    orgs: ["business"],
    iat: now,
    nbf: now,
    exp: now + TTL,
  })}`;
  const jwt = `${unsigned}.${sign(
    "RSA-SHA256",
    Buffer.from(unsigned),
    key
  ).toString("base64url")}`;
  // JWT creates a namespaced identity in the dedicated org; the org-scoped
  // service account enrolls it into the only folder-capable team before return.
  const org = await grafana("/api/org", membership.token);
  if (
    org.id !== 2 ||
    org.id !== membership.orgId ||
    org.name !== "Omi Business"
  ) {
    throw new Error("Grafana token targets an unexpected organization");
  }
  const user = await grafana("/api/user", jwt, undefined, true);
  if (
    user.login !== login ||
    user.orgId !== org.id ||
    user.isGrafanaAdmin ||
    !Number.isSafeInteger(user.id)
  ) {
    throw new Error("Grafana identity mismatch");
  }
  const team = await grafana(
    `/api/teams/${membership.teamId}`,
    membership.token
  );
  if (team.name !== "business-viewers")
    throw new Error("Grafana team mismatch");
  const path = `/api/teams/${membership.teamId}/members`;
  const members = await grafana(path, membership.token);
  if (
    !members.some((member: { userId: number }) => member.userId === user.id)
  ) {
    try {
      await grafana(path, membership.token, { userId: user.id });
    } catch {
      const after = await grafana(path, membership.token);
      if (
        !after.some((member: { userId: number }) => member.userId === user.id)
      ) {
        throw new Error("Grafana enrollment unavailable");
      }
    }
  }
  const url = new URL("/d/omi-tv-v2", ORIGIN);
  url.searchParams.set("kiosk", "");
  url.searchParams.set("refresh", "15m");
  url.searchParams.set("orgId", String(org.id));
  url.searchParams.set("auth_token", jwt);
  return { url: url.toString(), expiresAt: (now + TTL) * 1000 };
}
