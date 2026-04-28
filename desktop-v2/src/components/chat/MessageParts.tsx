import type { ChatMessage, ChatMessagePart } from "@/stores/chatStore";
import { MessageResponse } from "../ai-elements/message";
import { Reasoning } from "../ai-elements/reasoning";
import { Shimmer } from "../ai-elements/shimmer";
import { Tool, ToolGroup } from "../ai-elements/tool";
import { presentTool } from "./toolLabels";
import { TaskCardsBlock } from "./TaskCardsBlock";

type Group =
  | { kind: "text"; id: string; text: string; isStreaming?: boolean }
  | { kind: "reasoning"; part: Extract<ChatMessagePart, { type: "reasoning" }> }
  | { kind: "tools"; parts: Extract<ChatMessagePart, { type: "tool" }>[] }
  | { kind: "task_cards"; part: Extract<ChatMessagePart, { type: "task_cards" }> };

/**
 * Group consecutive tool parts into a single ToolGroup so multiple retrieval
 * steps don't each produce their own floating card.
 */
function groupParts(parts: ChatMessagePart[], fallbackStreaming?: boolean): Group[] {
  const groups: Group[] = [];
  for (const p of parts) {
    if (p.type === "tool") {
      const last = groups[groups.length - 1];
      if (last && last.kind === "tools") {
        last.parts.push(p);
      } else {
        groups.push({ kind: "tools", parts: [p] });
      }
    } else if (p.type === "reasoning") {
      groups.push({ kind: "reasoning", part: p });
    } else if (p.type === "task_cards") {
      groups.push({ kind: "task_cards", part: p });
    } else {
      groups.push({
        kind: "text",
        id: p.id,
        text: p.text,
        isStreaming: fallbackStreaming,
      });
    }
  }
  return groups;
}

export function MessageParts({ message }: { message: ChatMessage }) {
  const hasParts = message.parts && message.parts.length > 0;

  // Legacy messages persisted before parts were introduced: render content
  // directly. While streaming with no content yet, show a shimmer.
  if (!hasParts) {
    if (message.isStreaming && !message.content) {
      return <Shimmer>Thinking</Shimmer>;
    }
    return (
      <MessageResponse isAnimating={message.isStreaming}>
        {message.content}
      </MessageResponse>
    );
  }

  const groups = groupParts(message.parts!, message.isStreaming);
  const hasTextGroup = groups.some((g) => g.kind === "text");
  const hasRunningTool = groups.some(
    (g) => g.kind === "tools" && g.parts.some((p) => p.status === "running"),
  );

  return (
    <>
      {groups.map((g, i) => {
        if (g.kind === "text") {
          // Only animate the final text block while streaming.
          const isLast = i === groups.length - 1;
          return (
            <MessageResponse
              key={g.id}
              isAnimating={message.isStreaming && isLast}
            >
              {g.text}
            </MessageResponse>
          );
        }
        if (g.kind === "reasoning") {
          return (
            <Reasoning
              key={g.part.id}
              text={g.part.text}
              isStreaming={g.part.isStreaming}
            />
          );
        }
        if (g.kind === "task_cards") {
          return <TaskCardsBlock key={g.part.id} part={g.part} />;
        }
        return (
          <ToolGroup key={`tools-${i}`}>
            {g.parts.map((p) => {
              const presentation = presentTool(p.name);
              return (
                <Tool
                  key={p.id}
                  name={presentation.title}
                  iconUrl={p.iconUrl}
                  runningLabel={presentation.runningLabel}
                  status={p.status}
                  input={p.input?.summary}
                  output={p.output}
                  errorMessage={p.errorMessage}
                  defaultOpen={p.status === "running"}
                />
              );
            })}
          </ToolGroup>
        );
      })}
      {message.isStreaming && !hasTextGroup && !hasRunningTool && (
        <Shimmer>Thinking</Shimmer>
      )}
    </>
  );
}
