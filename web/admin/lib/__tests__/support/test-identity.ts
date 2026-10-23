import { NextResponse } from "next/server";
import { accessFor } from "@/lib/admin-access";
import { redactSensitiveFields } from "@/lib/sensitive-fields";

/**
 * An AdminIdentity for tests that stub requireScope. Same response
 * semantics as the real guard (lib/auth.ts): classified sensitive fields
 * (lib/sensitive-fields.ts) are redacted unless the doc's scopes unlock
 * their class. Defaults to an owner, which unlocks every scoped class —
 * credentials stay redacted for everyone — pass a narrower doc when a test
 * exercises the wall.
 */
export function testIdentity(
  doc: Record<string, unknown> = { owner: true },
  uid = "test-admin"
) {
  const access = accessFor(doc);
  return {
    uid,
    kind: "human" as const,
    email: null,
    access,
    json: (body: unknown, init?: ResponseInit, keep?: readonly string[]) =>
      NextResponse.json(
        redactSensitiveFields(body, { scopes: access.scopes, keep }),
        init
      ),
  };
}
