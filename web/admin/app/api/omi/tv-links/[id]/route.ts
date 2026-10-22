import { NextRequest, NextResponse } from "next/server";
import { requireScope } from "@/lib/auth";
import { hasScope } from "@/lib/admin-access";
import { revokeTvLink } from "@/lib/tv-links";
import { isSafeDocumentId } from "@/lib/firestore-doc-id.mjs";

export const dynamic = "force-dynamic";

export async function DELETE(
  request: NextRequest,
  props: { params: Promise<{ id: string }> }
) {
  const auth = await requireScope(request, "analytics:share");
  if (auth instanceof NextResponse) return auth;

  const params = await props.params;
  const id = params?.id;
  if (!id || !isSafeDocumentId(id)) {
    return auth.json({ error: "Missing id" }, { status: 400 });
  }

  try {
    const link = await revokeTvLink(id, {
      // Revocation stays open to every link manager, but the revoked link's
      // token is only echoed back to callers who may hold it.
      revealToken: hasScope(auth.access, "finance:read"),
    });
    if (!link) {
      return auth.json({ error: "Not found" }, { status: 404 });
    }
    return auth.json({ link });
  } catch (error) {
    console.error("revoke TV link:", error);
    return auth.json({ error: "Failed to revoke TV link" }, { status: 500 });
  }
}
