import { after, NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { wallPayload, wallSnapshotStore } from "@/lib/wall-cache";
import { wallPresentation } from "@/lib/wall-presentation";

import { localWallFixture } from "@/lib/wall-local-fixture";

export const dynamic = "force-dynamic";
export const maxDuration = 3600;
export async function GET(request: NextRequest) {
  const auth = await verifyAdmin(request);
  if (auth instanceof NextResponse) return auth;
  try {
    const payload =
      (await localWallFixture()) ||
      (await wallPayload(
        undefined,
        undefined,
        (work) =>
          after(async () => {
            await work;
          }),
        wallSnapshotStore()
      ));
    return NextResponse.json(wallPresentation(payload), {
      status:
        !payload.refreshing && payload.metrics.every((m) => m.value == null)
          ? 502
          : 200,
      headers: { "Cache-Control": "private, no-store" },
    });
  } catch {
    return NextResponse.json(
      { error: "Wall aggregate sources unavailable" },
      { status: 502 }
    );
  }
}
