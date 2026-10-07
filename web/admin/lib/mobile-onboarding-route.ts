import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import {
  getPayload,
  setPayload,
  withFreshness,
  MAX_PRECOMPUTED_AGE_MS,
} from "@/lib/payload-cache";
import {
  computeMobileOnboarding,
  MobileOnboardingKind,
  PostHogError,
} from "@/lib/mobile-onboarding-funnel";

export function mobileOnboardingCacheKey(
  kind: MobileOnboardingKind,
  days: number
) {
  return `onboarding:mobile:v1:${kind}:${days}`;
}

// Like macOS: compute is independently callable by precompute, while HTTP
// access uses admin verification. First-run and tutorial are precomputed; attach stays on-demand.
export function mobileOnboardingHandler(kind: MobileOnboardingKind) {
  return async function GET(request: NextRequest) {
    const auth = await verifyAdmin(request);
    if (auth instanceof NextResponse) return auth;
    const value = request.nextUrl.searchParams.get("days") ?? "30";
    const days = Number(value);
    if (
      !/^\d+$/.test(value) ||
      !Number.isInteger(days) ||
      days < 1 ||
      days > 365
    ) {
      return NextResponse.json(
        { error: "days must be an integer from 1 to 365" },
        { status: 400 }
      );
    }
    const key = mobileOnboardingCacheKey(kind, days);
    try {
      const cached = await getPayload<
        Awaited<ReturnType<typeof computeMobileOnboarding>>
      >(key, { maxAgeMs: MAX_PRECOMPUTED_AGE_MS });
      if (cached)
        return NextResponse.json(withFreshness(cached.data, cached.freshAt));
      const payload = await computeMobileOnboarding(kind, days);
      await setPayload(key, payload);
      return NextResponse.json(withFreshness(payload, Date.now()));
    } catch (error) {
      if (error instanceof PostHogError) {
        return NextResponse.json({ error: error.message }, { status: 502 });
      }
      if (
        error instanceof Error &&
        error.message === "PostHog credentials not configured"
      ) {
        return NextResponse.json({ error: error.message }, { status: 500 });
      }
      console.error("Error fetching mobile onboarding:", error);
      return NextResponse.json(
        { error: "Failed to fetch mobile onboarding data" },
        { status: 500 }
      );
    }
  };
}
