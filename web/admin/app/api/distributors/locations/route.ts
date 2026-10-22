import { NextRequest, NextResponse } from "next/server";
import { requireScope } from "@/lib/auth";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const authResult = await requireScope(request, "partners:read");
  if (authResult instanceof NextResponse) return authResult;

  try {
    const domain = process.env.SHOPIFY_STORE;
    const token = process.env.SHOPIFY_ACCESS_TOKEN;

    if (!domain || !token) {
      return authResult.json(
        { error: "Shopify credentials not configured" },
        { status: 500 }
      );
    }

    const res = await fetch(
      `https://${domain}/admin/api/2024-01/locations.json`,
      {
        headers: {
          "X-Shopify-Access-Token": token,
          "Content-Type": "application/json",
        },
        cache: "no-store",
      }
    );

    if (!res.ok) {
      const text = await res.text();
      console.error("Shopify locations error:", text);
      return authResult.json(
        { error: "Failed to fetch Shopify locations" },
        { status: 502 }
      );
    }

    const data = await res.json();

    const locations = (data.locations || [])
      .filter((loc: { active: boolean }) => loc.active)
      .map((loc: { id: number; name: string; active: boolean }) => ({
        id: `gid://shopify/Location/${loc.id}`,
        name: loc.name,
        isActive: loc.active,
      }));

    return authResult.json({ locations });
  } catch (error) {
    console.error("Error fetching locations:", error);
    return authResult.json(
      { error: "Failed to fetch locations" },
      { status: 500 }
    );
  }
}
