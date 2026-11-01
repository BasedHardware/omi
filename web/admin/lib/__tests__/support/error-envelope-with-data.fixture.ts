import { NextResponse } from "next/server";

/**
 * Negative fixture for the guard test in `lib/__tests__/route-scopes.test.ts`:
 * an `error` key must not mask scoped data in the same envelope. Never import.
 */
export function errorEnvelopeWithData(revenue: number) {
  return NextResponse.json(
    { error: "Totals unavailable", revenue },
    { status: 500 }
  );
}
