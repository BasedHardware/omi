import { NextResponse } from "next/server";

/**
 * Fixture for the guard test in `lib/__tests__/route-scopes.test.ts`: a bare
 * error envelope stays exempt from the guard's json() requirement. Never
 * import.
 */
export function bareErrorEnvelope(message: string) {
  return NextResponse.json({ error: message }, { status: 500 });
}
