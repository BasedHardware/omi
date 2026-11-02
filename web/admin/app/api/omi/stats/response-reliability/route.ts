import { NextRequest, NextResponse } from "next/server";

import { requireScope } from "@/lib/auth";
import admin, { getDb } from "@/lib/firebase/admin";
import { posthogResults } from "@/lib/posthog";
import {
  RELIABILITY_ROW_LIMIT,
  type ReliabilityChannel,
  responseReliabilityQueries,
} from "@/lib/response-reliability";
import { fetchTelemetryAggregates } from "@/lib/telemetry/client";
import { reliabilityReaderConfig } from "@/lib/telemetry/flags";
import { assembleResponseReliability } from "@/lib/telemetry/replacement-reliability";

export const dynamic = "force-dynamic";

function chunk<T>(items: T[], size: number): T[][] {
  const chunks: T[][] = [];
  for (let index = 0; index < items.length; index += size) {
    chunks.push(items.slice(index, index + size));
  }
  return chunks;
}

async function getReliabilityChannels(
  actorIds: string[]
): Promise<Map<string, ReliabilityChannel>> {
  const channelByActor = new Map<string, ReliabilityChannel>();
  const db = getDb();

  const snapshots = await Promise.all(
    chunk(actorIds, 30).map((actorIdChunk) =>
      db
        .collection("users")
        .where(admin.firestore.FieldPath.documentId(), "in", actorIdChunk)
        .select("update_channel")
        .get()
    )
  );
  for (const snapshot of snapshots) {
    for (const doc of snapshot.docs) {
      const updateChannel = String(doc.get("update_channel") || "");
      channelByActor.set(
        doc.id,
        updateChannel === "beta" || updateChannel === "staging"
          ? "beta"
          : "production"
      );
    }
  }

  for (const actorId of actorIds) {
    if (!channelByActor.has(actorId)) channelByActor.set(actorId, "production");
  }
  return channelByActor;
}

export async function GET(request: NextRequest) {
  const authResult = await requireScope(request, "analytics:read");
  if (authResult instanceof NextResponse) return authResult;

  const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
  const projectId = process.env.POSTHOG_PROJECT_ID;
  const host = (process.env.POSTHOG_HOST || "https://us.posthog.com").replace(
    /\/$/,
    ""
  );
  if (!apiKey || !projectId) {
    return authResult.json(
      { error: "PostHog credentials not configured" },
      { status: 500 }
    );
  }

  const requestedDays = Number.parseInt(
    request.nextUrl.searchParams.get("days") || "30",
    10
  );
  const days = Math.min(
    Math.max(Number.isFinite(requestedDays) ? requestedDays : 30, 7),
    90
  );
  const reader = reliabilityReaderConfig();
  const queries = responseReliabilityQueries(days);
  const [chatResult, voiceResult, aggregateResult] = await Promise.all([
    posthogResults(host, projectId, apiKey, queries.chat).then(
      (value) => ({ status: "fulfilled" as const, value }),
      (reason) => ({ status: "rejected" as const, reason })
    ),
    posthogResults(host, projectId, apiKey, queries.voice).then(
      (value) => ({ status: "fulfilled" as const, value }),
      (reason) => ({ status: "rejected" as const, reason })
    ),
    reader.enabled
      ? fetchTelemetryAggregates({
          adminUid: authResult.uid,
          days,
          channel: "all",
        })
      : Promise.resolve(null),
  ]);

  const chatAvailable = chatResult.status === "fulfilled";
  const posthogVoiceAvailable = voiceResult.status === "fulfilled";
  if (!chatAvailable && !posthogVoiceAvailable && !reader.enabled) {
    console.error("Response reliability queries failed", {
      chat: chatResult.status === "rejected" ? chatResult.reason : null,
      voice: voiceResult.status === "rejected" ? voiceResult.reason : null,
    });
    return authResult.json(
      { error: "Response reliability data is temporarily unavailable" },
      { status: 502 }
    );
  }

  if (!chatAvailable || !posthogVoiceAvailable) {
    console.warn("Response reliability data is partial", {
      chatAvailable,
      posthogVoiceAvailable,
      replacementReader: reader.enabled,
    });
  }

  const chatRows = chatAvailable ? chatResult.value : [];
  const voiceRows = posthogVoiceAvailable ? voiceResult.value : [];
  const truncated =
    chatRows.length >= RELIABILITY_ROW_LIMIT ||
    voiceRows.length >= RELIABILITY_ROW_LIMIT;
  if (truncated) {
    console.warn("Response reliability rows hit the HogQL limit", {
      chatRows: chatRows.length,
      voiceRows: voiceRows.length,
      limit: RELIABILITY_ROW_LIMIT,
    });
  }
  const replacementActorIds =
    aggregateResult?.body?.voice_rows.map((row) => row.actor_id) ?? [];
  const actorIds = Array.from(
    new Set(
      [
        ...chatRows.map((row) =>
          Array.isArray(row) ? String(row[6] ?? "") : ""
        ),
        ...voiceRows.map((row) =>
          Array.isArray(row) ? String(row[9] ?? "") : ""
        ),
        ...replacementActorIds,
      ].filter(Boolean)
    )
  );
  const channelByActor = await getReliabilityChannels(actorIds);
  const payload = assembleResponseReliability({
    days,
    chatRows,
    posthogVoiceRows: voiceRows,
    chatAvailable,
    posthogVoiceAvailable,
    posthogTruncated: truncated,
    channelByActor,
    reader,
    aggregate: aggregateResult,
  });
  if (!payload.availability.chat && !payload.availability.voice) {
    return authResult.json(
      { error: "Response reliability data is temporarily unavailable" },
      { status: 502 }
    );
  }

  return authResult.json(payload);
}
