import { NextRequest, NextResponse } from "next/server";
import { requireScope } from "@/lib/auth";
import type Stripe from "stripe";
import { getStripeRead } from "@/lib/stripe";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const authResult = await requireScope(request, "finance:read");
  if (authResult instanceof NextResponse) return authResult;

  const stripe = getStripeRead();

  try {
    const { searchParams } = new URL(request.url);
    const connectedAccountId = searchParams.get("connected_account_id");
    const limit = parseInt(searchParams.get("limit") || "100");
    const startingAfter = searchParams.get("starting_after");

    if (!connectedAccountId) {
      return authResult.json(
        { error: "connected_account_id is required" },
        { status: 400 }
      );
    }

    const params: Stripe.PayoutListParams = {
      limit,
    };

    if (startingAfter) {
      params.starting_after = startingAfter;
    }

    const payouts = await stripe.payouts.list(params, {
      stripeAccount: connectedAccountId,
    });

    return authResult.json({
      payouts: payouts.data,
      hasMore: payouts.has_more,
      totalCount: payouts.data.length,
    });
  } catch (error) {
    console.error("Error fetching payouts:", error);
    return authResult.json(
      { error: "Failed to fetch payouts" },
      { status: 500 }
    );
  }
}
