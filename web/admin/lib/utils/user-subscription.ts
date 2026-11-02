import admin, { getDb } from "@/lib/firebase/admin";
import { getRedis } from "@/lib/redis";
import { randomUUID } from "node:crypto";

// Same generation/writer protocol as backend/database/fsr_read_cache.py.
// Always fence admin writes, including when the backend rollout is off.
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

async function withSubscriptionInvalidation(
  uids: string[],
  write: () => Promise<unknown>
): Promise<void> {
  const writers = Array.from(new Set(uids));
  if (!writers.length) {
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
  const fences = writers.map((uid) => ({
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
  // One deadline for the operation, independent of employee count. Reserve half
  // for the end fence; Redis commands on the same connection retain FIFO order
  // even if a timed-out begin finishes after the durable write.
  const deadline = performance.now() + 250;
  async function invalidate(phase: "begin" | "end") {
    if (!redis) return;
    const client = redis;
    const pending = Promise.all(
      fences.map(async ({ root, token }) => {
        const args =
          phase === "begin" ? [token, ttl * 2] : [token, randomUUID(), ttl * 2];
        await client.eval(
          phase === "begin" ? BEGIN : END,
          2,
          root + ":generation",
          root + ":writers",
          ...args
        );
      })
    ).catch(() => {
      // Do not log user identifiers or provider exception payloads.
      console.warn(`Subscription cache invalidation failed phase=${phase}`);
    });
    const remaining = Math.max(0, deadline - performance.now());
    const wait = phase === "begin" ? Math.min(125, remaining) : remaining;
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      await Promise.race([
        pending,
        new Promise<void>((resolve) => {
          timer = setTimeout(() => {
            console.warn(
              `Subscription cache invalidation timed out phase=${phase}`
            );
            resolve();
          }, wait);
        }),
      ]);
    } finally {
      clearTimeout(timer);
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
