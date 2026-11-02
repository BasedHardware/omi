import { readFile } from "node:fs/promises";
import { WALL_DEFINITIONS, WallPayload } from "./wall-metrics";

/** Explicit development-only aggregate replay. Never creates a Firebase token or credential. */
export async function localWallFixture(): Promise<WallPayload | null> {
  const path = process.env.OMI_TV_LOCAL_FIXTURE_PATH;
  if (!path) return null;
  if (
    process.env.NODE_ENV === "production" ||
    process.env.DEV_BYPASS_AUTH !== "1"
  )
    throw new Error("Wall fixtures require development auth bypass");
  const data = JSON.parse(await readFile(path, "utf8")) as WallPayload;
  if (
    !Array.isArray(data.metrics) ||
    WALL_DEFINITIONS.some(([id]) => !data.metrics.some((m) => m.id === id))
  )
    throw new Error("Incomplete local wall fixture");
  return {
    ...data,
    partial: true,
    metrics: data.metrics.map((m) => ({
      ...m,
      status: m.value == null ? "null" : "proxy",
      reason: `LOCAL AGGREGATE REPLAY · ${m.reason || ""}`,
    })),
  };
}
