import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { revokeTvLink } from "@/lib/tv-links";

export const dynamic = "force-dynamic";

export async function DELETE(
  request: NextRequest,
  props: { params: Promise<{ id: string }> }
) {
  const auth = await verifyAdmin(request);
  if (auth instanceof NextResponse) return auth;

  const params = await props.params;
  const id = params?.id;
  if (!id) {
    return NextResponse.json({ error: "Missing id" }, { status: 400 });
  }

  try {
    const link = await revokeTvLink(id);
    if (!link) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }
    return NextResponse.json({ link });
  } catch (error) {
    console.error("revoke TV link:", error);
    return NextResponse.json(
      { error: "Failed to revoke TV link" },
      { status: 500 }
    );
  }
}
