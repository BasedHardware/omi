import { describe, expect, it } from "vitest";
import { contentBlockFallbackText } from "../src/runtime/content-block-fallback.js";
import type { ConversationContentBlock } from "../src/runtime/types.js";

describe("structured chat fallback text", () => {
  it("derives the meeting headline from the conversation block", () => {
    expect(contentBlockFallbackText({
      type: "conversationLink",
      id: "meeting-1",
      conversationId: "conversation-1",
      summary: "Founders explore AI memory",
      recommendedActionItems: [],
    })).toBe("Meeting notes ready - Founders explore AI memory");
  });

  it("keeps every content-block variant non-empty for unaware clients", () => {
    const blocks: ConversationContentBlock[] = [
      { type: "text", id: "1", text: "" },
      { type: "toolCall", id: "2", name: "search", status: "completed" },
      { type: "thinking", id: "3", text: "" },
      { type: "discoveryCard", id: "4", title: "Result", summary: "Summary", fullText: "Full" },
      {
        type: "questionCard", id: "5", questionId: "question-1", text: "Choose?",
        subject: { kind: "goal", id: "goal-1" },
        options: [{ optionId: "yes", label: "Yes", preparedAnswer: "Yes" }],
      },
      { type: "taskCard", id: "6", taskId: "task-1" },
      { type: "goalLink", id: "7", goalId: "goal-1", summary: "Ship it" },
      { type: "captureLink", id: "8", conversationId: "capture-1", summary: "Capture" },
      {
        type: "conversationLink", id: "9", conversationId: "meeting-1", summary: "Meeting",
        recommendedActionItems: [],
      },
      { type: "memoryLink", id: "10", memoryId: "memory-1", summary: "Preference" },
      { type: "citation", id: "11", ordinal: 1, kind: "web", sourceId: "source-1" },
      {
        type: "agentSpawn", id: "12", sessionId: "session-1", runId: "run-1",
        title: "Research", objective: "Find evidence",
      },
      {
        type: "agentCompletion", id: "13", title: "Research", promptSnippet: "Find",
        output: "Found evidence", status: "succeeded",
      },
    ];

    expect(blocks.map(contentBlockFallbackText).every((text) => text.trim().length > 0)).toBe(true);
  });
});
