import { NextRequest } from "next/server";

const b64 = (value: unknown) =>
  Buffer.from(JSON.stringify(value)).toString("base64url");

/**
 * A token shaped like a Firebase ID token for `uid`. It is not signed: tests
 * mock `verifyFirebaseToken` with `decodeTestFirebaseToken`, so the real
 * issuer dispatch and requireScope still run.
 */
export function firebaseToken(uid: string) {
  return `${b64({ alg: "none" })}.${b64({
    iss: "https://securetoken.google.com/omi-test",
    uid,
  })}.sig`;
}

export function decodeTestFirebaseToken(token: string) {
  try {
    const { uid } = JSON.parse(
      Buffer.from(token.split(".")[1], "base64url").toString()
    );
    return typeof uid === "string" ? { uid } : null;
  } catch {
    return null;
  }
}

export function adminRequest(
  token: string | null,
  method: string,
  path: string,
  body?: unknown
) {
  return new NextRequest(`https://admin.omi.me${path}`, {
    method,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}
