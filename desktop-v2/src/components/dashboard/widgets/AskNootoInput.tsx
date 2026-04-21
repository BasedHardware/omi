import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { ChatStatus } from "ai";
import { useChatStore } from "@/stores/chatStore";
import {
  PromptInput,
  PromptInputActionAddAttachments,
  PromptInputActionAddScreenshot,
  PromptInputActionMenu,
  PromptInputActionMenuContent,
  PromptInputActionMenuTrigger,
  PromptInputBody,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
  type PromptInputMessage,
} from "@/components/ai-elements/prompt-input";
import { Suggestion, Suggestions } from "@/components/ai-elements/suggestion";

const SUGGESTIONS = [
  "What did I work on today?",
  "Summarize my screen time",
  "What's next on my plate?",
  "Draft a reply to my last email",
  "Help me plan tomorrow",
];

/**
 * Dashboard's "Ask Nooto" composer. Uses the same ai-elements primitives
 * as the full Chat page so the two surfaces feel identical. On submit,
 * the message is enqueued in chatStore and the user is routed to /chat
 * to land on the streaming response.
 */
export function AskNootoInput() {
  const navigate = useNavigate();
  const sendMessage = useChatStore((s) => s.sendMessage);
  const newSession = useChatStore((s) => s.newSession);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const [text, setText] = useState("");

  const chatStatus: ChatStatus = isStreaming ? "streaming" : "ready";

  const fire = (payload: string) => {
    const trimmed = payload.trim();
    if (!trimmed || isStreaming) return;
    setText("");
    // Always start a fresh session — the dashboard composer is the
    // "new conversation" entry point. Appending to the last chat would
    // mix unrelated questions into a single thread.
    newSession();
    void sendMessage(trimmed);
    navigate("/chat");
  };

  const handleSubmit = useCallback(
    (message: PromptInputMessage) => fire(message.text),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [isStreaming, sendMessage, newSession, navigate],
  );

  const handleSuggestion = useCallback(
    (suggestion: string) => fire(suggestion),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [isStreaming, sendMessage, newSession, navigate],
  );

  return (
    <section className="flex flex-col gap-3">
      <Suggestions>
        {SUGGESTIONS.map((s) => (
          <Suggestion key={s} suggestion={s} onClick={handleSuggestion} />
        ))}
      </Suggestions>

      <PromptInput onSubmit={handleSubmit} className="w-full">
        <PromptInputBody>
          <PromptInputTextarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="What would you like to know?"
          />
        </PromptInputBody>
        <PromptInputFooter>
          <PromptInputTools>
            <PromptInputActionMenu>
              <PromptInputActionMenuTrigger />
              <PromptInputActionMenuContent>
                <PromptInputActionAddAttachments />
                <PromptInputActionAddScreenshot />
              </PromptInputActionMenuContent>
            </PromptInputActionMenu>
          </PromptInputTools>
          <PromptInputSubmit
            status={chatStatus}
            disabled={chatStatus === "ready" && !text.trim()}
          />
        </PromptInputFooter>
      </PromptInput>
    </section>
  );
}
