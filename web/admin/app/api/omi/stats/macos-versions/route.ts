import { NextRequest, NextResponse } from "next/server";
import admin, { getDb } from "@/lib/firebase/admin";
import { verifyAdmin } from "@/lib/auth";

export const dynamic = "force-dynamic";

const VERSION_COLORS = [
  "#6366f1",
  "#f59e0b",
  "#22c55e",
  "#ef4444",
  "#06b6d4",
  "#a855f7",
  "#f97316",
  "#14b8a6",
  "#eab308",
  "#8b5cf6",
  "#ec4899",
  "#84cc16",
];

const CHANNEL_COLORS: Record<string, string> = {
  Beta: "#f59e0b",
  Production: "#6366f1",
};

type Breakdown = {
  label: string;
  value: number;
  color: string;
};

async function posthogQuery(host: string, projectId: string, apiKey: string, query: string) {
  const response = await fetch(`${host}/api/projects/${projectId}/query/`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({
      query: {
        kind: "HogQLQuery",
        query,
      },
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`PostHog API error: ${response.status} ${text}`);
  }

  const raw = await response.json();
  return Array.isArray(raw.results) ? raw.results : [];
}

function chunk<T>(items: T[], size: number) {
  const chunks: T[][] = [];
  for (let index = 0; index < items.length; index += size) {
    chunks.push(items.slice(index, index + size));
  }
  return chunks;
}

async function getUserChannels(userIds: string[]) {
  const db = getDb();
  const channels = new Map<string, string>();

  for (const userIdChunk of chunk(userIds, 30)) {
    if (userIdChunk.length === 0) continue;

    const snapshot = await db
      .collection("users")
      .where(admin.firestore.FieldPath.documentId(), "in", userIdChunk)
      .select("update_channel")
      .get();

    for (const doc of snapshot.docs) {
      channels.set(doc.id, String(doc.get("update_channel") || ""));
    }
  }

  return channels;
}

function breakdownFromEntries(entries: [string, number][], colors: string[] | Record<string, string>): Breakdown[] {
  return entries.map(([label, value], index) => ({
    label,
    value,
    color: Array.isArray(colors) ? colors[index % colors.length] : colors[label] || "#94a3b8",
  }));
}

function formatTodayLabel() {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date());
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
    const projectId = process.env.POSTHOG_PROJECT_ID;
    const host = (process.env.POSTHOG_HOST || "https://us.posthog.com").replace(/\/$/, "");

    if (!apiKey || !projectId) {
      return NextResponse.json({ error: "PostHog credentials not configured" }, { status: 500 });
    }

    const activeUsersQuery = `
      SELECT
        distinct_id AS actor_id,
        argMax(
          COALESCE(
            nullIf(properties.app_version, ''),
            nullIf(properties.$app_version, ''),
            'unknown'
          ),
          timestamp
        ) AS app_version
      FROM events
      WHERE event = 'App Became Active'
        AND properties.$os_name = 'macOS'
        AND toDate(timestamp) = today()
      GROUP BY actor_id
      ORDER BY actor_id ASC
      LIMIT 100000
    `;

    const rows = (await posthogQuery(host, projectId, apiKey, activeUsersQuery)) as [unknown, unknown][];
    const activeUsers = rows
      .map((row: [unknown, unknown]) => ({
        userId: String(row[0] ?? "").trim(),
        appVersion: String(row[1] ?? "unknown").trim() || "unknown",
      }))
      .filter((row) => row.userId.length > 0);

    if (activeUsers.length === 0) {
      return NextResponse.json({
        date: formatTodayLabel(),
        activeUsers: 0,
        channelBreakdown: [],
        versionBreakdown: [],
      });
    }

    const channelMap = await getUserChannels(activeUsers.map((user) => user.userId));

    const channelCounts = new Map<string, number>();
    const versionCounts = new Map<string, number>();

    for (const user of activeUsers) {
      versionCounts.set(user.appVersion, (versionCounts.get(user.appVersion) || 0) + 1);

      const channel = channelMap.get(user.userId);
      const channelLabel = channel === "beta" || channel === "staging" ? "Beta" : "Production";
      channelCounts.set(channelLabel, (channelCounts.get(channelLabel) || 0) + 1);
    }

    const channelBreakdown = breakdownFromEntries(
      Array.from(channelCounts.entries()).sort((a, b) => b[1] - a[1]),
      CHANNEL_COLORS
    );

    const versionBreakdown = breakdownFromEntries(
      Array.from(versionCounts.entries()).sort((a, b) => b[1] - a[1]),
      VERSION_COLORS
    );

    return NextResponse.json({
      date: formatTodayLabel(),
      activeUsers: activeUsers.length,
      channelBreakdown,
      versionBreakdown,
    });
  } catch (error: any) {
    console.error("macOS version stats error:", error);
    return NextResponse.json(
      { error: error.message || "Failed to fetch macOS version stats" },
      { status: 500 }
    );
  }
}
