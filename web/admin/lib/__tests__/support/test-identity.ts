import { NextResponse } from "next/server";
import { accessFor, hasScope } from "@/lib/admin-access";
import { redactFinancialFields } from "@/lib/financial-fields";

/**
 * An AdminIdentity for tests that stub requireScope. Same response
 * semantics as the real guard (lib/auth.ts): financial fields are redacted
 * unless the doc grants finance:read. Defaults to an owner, which skips
 * redaction — pass a narrower doc when a test exercises the wall.
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
        hasScope(access, "finance:read")
          ? body
          : redactFinancialFields(body, { keep }),
        init
      ),
  };
}
