import admin, { getDb } from "@/lib/firebase/admin";
import { getRedis } from "@/lib/redis";
import { createHash, randomUUID } from "node:crypto";

// Same cohort and generation/writer protocol as backend/utils/s4_read_cache.py.
const BEGIN = `
redis.call('SADD', KEYS[2], ARGV[1])
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
return 1
`;
const END = `
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
redis.call('SREM', KEYS[2], ARGV[1])
return 1
`;

function subscriptionCacheEnabled(uid: string): boolean {
  try {
    const percent = JSON.parse(
      process.env.FIRESTORE_READ_LEVERS || "{}"
    )?.subscription_cache;
    if (!Number.isInteger(percent) || percent < 0 || percent > 100)
      return false;
    const bucket =
      createHash("sha256")
        .update(`subscription_cache:${uid}`)
        .digest()
        .readBigUInt64BE() % BigInt(100);
    return bucket < BigInt(percent);
  } catch {
    return false;
  }
}

async function withSubscriptionInvalidation(
  uids: string[],
  write: () => Promise<unknown>
): Promise<void> {
  const enabled = Array.from(new Set(uids)).filter(subscriptionCacheEnabled);
  if (!enabled.length) {
    await write();
    return;
  }
  // Reuse the existing client; durable writes must still work during a Redis outage.
  let redis: ReturnType<typeof getRedis> = null;
  try {
    redis = getRedis();
  } catch {
    console.warn("Subscription cache client unavailable");
  }
  const fences = enabled.map((uid) => ({
    // Python json.dumps uses ASCII escapes, including surrogate pairs.
    root:
      "fsr:s4:v2:" +
      JSON.stringify(["subscription_cache", uid]).replace(
        /[\u007f-\uffff]/g,
        (character) =>
          "\\u" + character.charCodeAt(0).toString(16).padStart(4, "0")
      ),
    token: randomUUID(),
  }));
  const parsedTtl = Number(process.env.FSR_SUBSCRIPTION_TTL_SECONDS ?? 60);
  const ttl = Number.isInteger(parsedTtl)
    ? Math.min(60, Math.max(1, parsedTtl))
    : 60;
  async function invalidate(phase: "begin" | "end") {
    if (!redis) return;
    for (const { root, token } of fences) {
      try {
        const args =
          phase === "begin" ? [token, ttl * 2] : [token, randomUUID(), ttl * 2];
        await redis.eval(
          phase === "begin" ? BEGIN : END,
          2,
          root + ":generation",
          root + ":writers",
          ...args
        );
      } catch {
        // Do not log user identifiers or provider exception payloads.
        console.warn(`Subscription cache invalidation failed phase=${phase}`);
      }
    }
  }
  await invalidate("begin");
  try {
    await write();
  } finally {
    await invalidate("end");
  }
}

// Function to update user subscription details for all employees
export async function updateUserSubscriptionDetails(
  employees: any[],
  subscriptionData: any
) {
  if (!subscriptionData) return;

  const db = getDb();
  const batch = db.batch();

  // Create user subscription data (without customer_id)
  const userSubscription = {
    subscription_id: subscriptionData.subscription_id,
    current_period_end: subscriptionData.current_period_end,
    cancel_at_period_end: subscriptionData.cancel_at_period_end,
    plan: subscriptionData.plan,
    status: subscriptionData.status,
  };

  // Update each employee's user document
  for (const employee of employees) {
    if (employee.uid) {
      const userRef = db.collection("users").doc(employee.uid);
      batch.update(userRef, {
        subscription: userSubscription,
        stripe_customer_id: subscriptionData.customer_id,
      });
    }
  }

  await withSubscriptionInvalidation(
    employees
      .filter((employee) => employee.uid)
      .map((employee) => employee.uid),
    () => batch.commit()
  );
}

// Function to remove subscription details from user documents
export async function removeUserSubscriptionDetails(employees: any[]) {
  const db = getDb();
  const batch = db.batch();

  // Remove subscription details from each employee's user document
  for (const employee of employees) {
    if (employee.uid) {
      const userRef = db.collection("users").doc(employee.uid);
      batch.update(userRef, {
        subscription: admin.firestore.FieldValue.delete(),
        stripe_customer_id: admin.firestore.FieldValue.delete(),
      });
    }
  }

  await withSubscriptionInvalidation(
    employees
      .filter((employee) => employee.uid)
      .map((employee) => employee.uid),
    () => batch.commit()
  );
}

// Function to update subscription for a single user
export async function updateSingleUserSubscription(
  userId: string,
  subscriptionData: any
) {
  if (!subscriptionData) return;

  const db = getDb();
  const userSubscription = {
    subscription_id: subscriptionData.subscription_id,
    current_period_end: subscriptionData.current_period_end,
    cancel_at_period_end: subscriptionData.cancel_at_period_end,
    plan: subscriptionData.plan,
    status: subscriptionData.status,
  };

  const userRef = db.collection("users").doc(userId);
  await withSubscriptionInvalidation([userId], () =>
    userRef.update({
      subscription: userSubscription,
      stripe_customer_id: subscriptionData.customer_id,
    })
  );
}
