import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { getDb } from "@/lib/firebase/admin";
import { getPayload, setPayload, withFreshness } from "@/lib/payload-cache";
import { toGrafanaActivationPayload } from "@/lib/activation-compat";
import {
  rollUpActivationCohort,
  type ActivationCohortMember,
  type ActivationSeries,
} from "@/lib/growth-metrics";

export const dynamic = "force-dynamic";
export const maxDuration = 3600;

const DAY_MS = 86_400_000;
const MATURITY_DAYS = 7;
const PAGE = 500;
const CONCURRENCY = 16;

// `created_at` is null on user documents written by the current signup path;
// `signup_platform_at` is the field that is actually populated. Cohorting on
// `created_at` silently returns almost nobody.
const SIGNUP_FIELD = "signup_platform_at";

export function activationCacheKey(days: number): string {
  return `activation:v1:macos:${days}`;
}

/**
 * macOS activation measured from conversation records rather than telemetry.
 *
 * The PostHog series counts the desktop `Memory Created` event, which older
 * builds cannot emit at all, so it reports build age rather than behaviour.
 * A conversation document exists whether or not the client managed to report
 * it, which makes this the only source that can answer the question today.
 */
export async function computeActivation(
  days: number,
): Promise<ActivationSeries & { erroredUsers: number }> {
  const db = getDb();
  const now = Date.now();
  const windowStart = new Date(now - days * DAY_MS);
  const maturedBefore = new Date(now - MATURITY_DAYS * DAY_MS);

  // Filtering on signup_os alongside a signup_platform_at range needs a
  // composite index that does not exist on this project, so the range is the
  // query and the platform is filtered here.
  const cohort: { uid: string; signupAt: Date }[] = [];
  let cursor: FirebaseFirestore.QueryDocumentSnapshot | null = null;
  for (;;) {
    let query = db
      .collection("users")
      .where(SIGNUP_FIELD, ">", windowStart)
      .orderBy(SIGNUP_FIELD, "asc")
      .limit(PAGE);
    if (cursor) query = query.startAfter(cursor);

    const snap = await query.get();
    if (snap.empty) break;

    for (const doc of snap.docs) {
      const data = doc.data();
      if (data.signup_os !== "macos") continue;
      const signupAt: Date | undefined = data[SIGNUP_FIELD]?.toDate?.();
      // Signups inside the maturity window have not had their full 7 days, so
      // counting them would pit a guaranteed-zero numerator against a real
      // denominator.
      if (!signupAt || signupAt > maturedBefore) continue;
      cohort.push({ uid: doc.id, signupAt });
    }

    if (snap.size < PAGE) break;
    cursor = snap.docs[snap.docs.length - 1];
  }

  // `null` means the read failed. It must stay distinct from `false`: scoring an
  // unreadable user as "did not activate" is the same mistake this whole metric
  // exists to undo, just one layer down.
  const activated = new Array<boolean | null>(cohort.length).fill(null);
  let next = 0;

  async function worker(): Promise<void> {
    for (;;) {
      const i = next++;
      if (i >= cohort.length) return;
      const { uid, signupAt } = cohort[i];
      const windowEnd = new Date(signupAt.getTime() + MATURITY_DAYS * DAY_MS);
      try {
        const agg = await db
          .collection("users")
          .doc(uid)
          .collection("conversations")
          .where("created_at", ">=", signupAt)
          .where("created_at", "<=", windowEnd)
          .count()
          .get();
        activated[i] = agg.data().count > 0;
      } catch {
        // Left null: reported via erroredUsers and dropped from the cohort, so
        // a partial read shrinks the sample instead of depressing the rate.
      }
    }
  }

  await Promise.all(
    Array.from({ length: Math.min(CONCURRENCY, cohort.length) }, worker),
  );

  const members: ActivationCohortMember[] = [];
  let erroredUsers = 0;
  cohort.forEach((m, i) => {
    const result = activated[i];
    if (result === null) {
      erroredUsers += 1;
      return;
    }
    members.push({ signupAt: m.signupAt.toISOString(), activated: result });
  });

  return { ...rollUpActivationCohort(members), erroredUsers };
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    // A non-numeric `days` would otherwise reach Firestore as NaN date
    // arithmetic and 500 the route.
    const requestedDays = parseInt(
      request.nextUrl.searchParams.get("days") || "60",
      10,
    );
    const days = Number.isFinite(requestedDays)
      ? Math.min(Math.max(requestedDays, 1), 180)
      : 60;
    const key = activationCacheKey(days);

    const cached =
      await getPayload<Awaited<ReturnType<typeof computeActivation>>>(key);
    if (cached) {
      return NextResponse.json(
        withFreshness(toGrafanaActivationPayload(cached.data), cached.freshAt),
      );
    }

    const payload = await computeActivation(days);
    await setPayload(key, payload);
    return NextResponse.json(
      withFreshness(toGrafanaActivationPayload(payload), Date.now()),
    );
  } catch (error: any) {
    console.error("Activation error:", error);
    return NextResponse.json(
      { error: error.message || "Failed to compute activation" },
      { status: 500 },
    );
  }
}
