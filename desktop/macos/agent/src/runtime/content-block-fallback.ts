import type { ConversationContentBlock, ConversationResource } from "./types.js";

const MAX_BACKEND_MESSAGE_TEXT_LENGTH = 100_000;

/**
 * Human-readable degradation contract for every structured chat block.
 *
 * Keeping this switch exhaustive makes a new block type a compile error until
 * its unaware-client representation is defined. The rich desktop renderer
 * still consumes the structured block; this text is the canonical fallback
 * carried by the ordinary message field for every other client.
 */
export function contentBlockFallbackText(block: ConversationContentBlock): string {
  switch (block.type) {
    case "text":
      return nonEmptyText(block.text, "Message");
    case "toolCall":
      return labelledText("Tool", block.name, block.output ?? block.inputSummary);
    case "thinking":
      return labelledText("Thinking", block.text);
    case "discoveryCard":
      return labelledText("Discovery", block.title, block.summary);
    case "questionCard":
      return nonEmptyText(block.text, "Question");
    case "taskCard":
      return "Task";
    case "goalLink":
      return labelledText("Goal", block.summary);
    case "captureLink":
      return labelledText("Capture", block.summary);
    case "conversationLink":
      return labelledText("Meeting notes ready", block.summary);
    case "memoryLink":
      return labelledText("Memory", block.summary);
    case "citation":
      return labelledText("Source", block.title, block.preview);
    case "agentSpawn":
      return labelledText("Agent started", block.title, block.objective);
    case "agentCompletion":
      return labelledText("Agent completed", block.title, block.output);
    default: {
      const exhaustive: never = block;
      return exhaustive;
    }
  }
}

export function structuredTurnFallbackText(
  blocks: readonly ConversationContentBlock[],
  resources: readonly ConversationResource[],
): string {
  const lines = blocks.map(contentBlockFallbackText);
  lines.push(...resources.map((resource) => labelledText("Attachment", resource.title)));
  return lines.join("\n").slice(0, MAX_BACKEND_MESSAGE_TEXT_LENGTH).trim();
}

function labelledText(label: string, ...parts: Array<string | undefined>): string {
  const detail = parts
    .map((part) => part?.trim() ?? "")
    .filter((part, index, values) => part.length > 0 && values.indexOf(part) === index)
    .join(" - ");
  return detail ? `${label} - ${detail}` : label;
}

function nonEmptyText(value: string, fallback: string): string {
  return value.trim() || fallback;
}
