import { computeWall, WallPayload } from "./wall-metrics";
import { isoDay, utcDay } from "./qualified-activity";

// Read-only wall: bounded/coalesced payload cache; no Firestore writes or stale-on-error.
let cached: { day: string; at: number; payload: WallPayload } | null = null;
let flight: { day: string; promise: Promise<WallPayload> } | null = null;
export async function wallPayload(
  now = new Date(),
  compute = computeWall
): Promise<WallPayload> {
  const day = isoDay(utcDay(now));
  if (cached?.day === day && now.getTime() - cached.at < 15 * 60_000)
    return cached.payload;
  if (flight?.day === day) return flight.promise;
  const promise = compute(undefined, now)
    .then((payload) => {
      cached = { day, at: now.getTime(), payload };
      return payload;
    })
    .finally(() => {
      if (flight?.promise === promise) flight = null;
    });
  flight = { day, promise };
  return promise;
}
export function resetWallCache() {
  cached = null;
  flight = null;
}
