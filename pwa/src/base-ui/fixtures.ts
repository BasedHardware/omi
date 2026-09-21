import type { DesktopReadOutcomes } from "../../../react-native/src/desktopReadClient";

// Example output for a synthetic profile, not a live AI response.
export const previewDailyIdea = {
  interests: ["Walking", "Creative projects"],
  title: "Take your ideas on a detour.",
  body: "On your next walk, take one unfamiliar turn and notice three things you usually miss. Bring one back as an idea for your next project.",
  prompt:
    "Give me a playful 10-minute walking challenge that combines getting outside with noticing design details. Keep it low-key and easy to try today.",
};

// Synthetic, local-only data. Never connected to an account or persisted.
export function previewOutcomes(empty = false): DesktopReadOutcomes {
  const now = new Date();
  const due = new Date(now);
  due.setHours(23, 59, 59, 999);
  const page = {
    windowStatus: "complete" as const,
    complete: true,
    hasMore: false,
    nextCursor: null,
    completenessStatus: "complete" as const,
    reasons: [],
  };
  return {
    tasks: {
      status: "success",
      value: {
        apiContract: "omi",
        accountEpoch: null,
        page,
        items: empty
          ? []
          : [
              "Send the notes from today’s conversation",
              "Make time for a long walk",
              "Review the ideas for the next release",
            ].map((title, index) => ({
              kind: "task",
              id: `task-${index}`,
              title,
              summary: "",
              searchableText: title,
              completed: index === 1,
              completedAt: null,
              dueAt: index === 0 ? due.getTime() : null,
              owner: "You",
              source: "desktop",
              provenance: [],
              sortOrder: index,
              indentLevel: 0,
              createdAt: null,
              updatedAt: null,
              revision: null,
            })),
      },
    },
    conversations: {
      status: "success",
      value: {
        page,
        items: empty
          ? []
          : [
              "A thoughtful start to the week",
              "Planning a quieter workspace",
            ].map((title, index) => ({
              kind: "conversation",
              id: `conversation-${index}`,
              title,
              summary:
                index === 0
                  ? "A few ideas, a clear next step, and time to think."
                  : "Less visual noise. More room for the work that matters.",
              searchableText: title,
              createdAt: new Date(
                now.getTime() - (index + 1) * 3600000
              ).toISOString(),
              updatedAt: null,
              startedAt: null,
              finishedAt: null,
              starred: index === 1,
              status: "completed",
              source: "desktop",
              visibility: "private",
              folderId: null,
              locked: false,
              discarded: false,
            })),
      },
    },
    memories: { status: "success", value: { items: [], page } },
  };
}
