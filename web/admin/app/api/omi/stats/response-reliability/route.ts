import { NextRequest, NextResponse } from "next/server";

import { verifyAdmin } from "@/lib/auth";
import admin, { getDb } from "@/lib/firebase/admin";
import { posthogResults } from "@/lib/posthog";
import {
  buildChannelReliabilityPayloads,
  buildResponseReliabilityPayload,
  type ReliabilityChannel,
  responseReliabilityQueries,
} from "@/lib/response-reliability";

export const dynamic = "force-dynamic";

function chunk<T>(items: T[], size: number): T[][] {
  const chunks: T[][] = [];
  for (let index = 0; index < items.length; index += size) {
    chunks.push(items.slice(index, index + size));
  }
  return chunks;
}

async function getReliabilityChannels(
  actorIds: string[],
): Promise<Map<string, ReliabilityChannel>> {
  const channelByActor = new Map<string, ReliabilityChannel>();
  const db = getDb();

  for (const actorIdChunk of chunk(actorIds, 30)) {
    const snapshot = await db
      .collection("users")
      .where(admin.firestore.FieldPath.documentId(), "in", actorIdChunk)
      .select("update_channel")
      .get();
    for (const doc of snapshot.docs) {
      const updateChannel = String(doc.get("update_channel") || "");
      channelByActor.set(
        doc.id,
        updateChannel === "beta" || updateChannel === "staging"
          ? "beta"
          : "production",
      );
    }
  }

  for (const actorId of actorIds) {
    if (!channelByActor.has(actorId)) channelByActor.set(actorId, "production");
  }
  return channelByActor;
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
  const projectId = process.env.POSTHOG_PROJECT_ID;
  const host = (process.env.POSTHOG_HOST || "https://us.posthog.com").replace(
    /\/$/,
    "",
  );
  if (!apiKey || !projectId) {
    return NextResponse.json(
      { error: "PostHog credentials not configured" },
      { status: 500 },
    );
  }

  const requestedDays = Number.parseInt(
    request.nextUrl.searchParams.get("days") || "30",
    10,
  );
  const days = Math.min(
    Math.max(Number.isFinite(requestedDays) ? requestedDays : 30, 7),
    90,
  );
  const queries = responseReliabilityQueries(days);
  const [chatResult, voiceResult] = await Promise.allSettled([
    posthogResults(host, projectId, apiKey, queries.chat),
    posthogResults(host, projectId, apiKey, queries.voice),
  ]);

  const chatAvailable = chatResult.status === "fulfilled";
  const voiceAvailable = voiceResult.status === "fulfilled";
  if (!chatAvailable && !voiceAvailable) {
    console.error("Response reliability queries failed", {
      chat: chatResult.status === "rejected" ? chatResult.reason : null,
      voice: voiceResult.status === "rejected" ? voiceResult.reason : null,
    });
    return NextResponse.json(
      { error: "Response reliability data is temporarily unavailable" },
      { status: 502 },
    );
  }

  if (!chatAvailable || !voiceAvailable) {
    console.warn("Response reliability data is partial", {
      chatAvailable,
      voiceAvailable,
    });
  }

  const chatRows = chatAvailable ? chatResult.value : [];
  const voiceRows = voiceAvailable ? voiceResult.value : [];
  const actorIds = Array.from(
    new Set(
      [
        ...chatRows.map((row) =>
          Array.isArray(row) ? String(row[6] ?? "") : "",
        ),
        ...voiceRows.map((row) =>
          Array.isArray(row) ? String(row[9] ?? "") : "",
        ),
      ].filter(Boolean),
    ),
  );
  const channelByActor = await getReliabilityChannels(actorIds);
  const aggregate = buildResponseReliabilityPayload({
    days,
    chatRows,
    voiceRows,
    chatAvailable,
    voiceAvailable,
  });

  return NextResponse.json({
    ...aggregate,
    channels: buildChannelReliabilityPayloads({
      days,
      chatRows,
      voiceRows,
      chatAvailable,
      voiceAvailable,
      channelByActor,
    }),
  });
}
