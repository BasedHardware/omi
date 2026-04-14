/**
 * Chat page — AI chat via Gemini.
 *
 * Calls Gemini directly for streaming responses.
 * Local screen capture data is automatically injected as context when
 * the user asks about their activity.
 * Messages are persisted locally via tauri-plugin-store.
 */

import { useCallback, useState } from "react";
import { useChatStore } from "../../stores/chatStore";
import type { ChatMessage } from "../../stores/chatStore";
import {
  Conversation,
  ConversationContent,
  ConversationEmptyState,
  ConversationScrollButton,
} from "../ai-elements/conversation";
import {
  Message,
  MessageActions,
  MessageAction,
  MessageContent,
  MessageResponse,
} from "../ai-elements/message";
import {
  PromptInput,
  PromptInputBody,
  PromptInputTextarea,
  PromptInputHeader,
  PromptInputFooter,
  PromptInputTools,
  PromptInputSubmit,
  PromptInputActionMenu,
  PromptInputActionMenuTrigger,
  PromptInputActionMenuContent,
  PromptInputActionAddAttachments,
  PromptInputActionAddScreenshot,
  usePromptInputAttachments,
  type PromptInputMessage,
} from "../ai-elements/prompt-input";
import {
  Attachment,
  AttachmentPreview,
  AttachmentRemove,
  Attachments,
} from "../ai-elements/attachments";
import { Suggestions, Suggestion } from "../ai-elements/suggestion";
import {
  Trash2,
  SparklesIcon,
  CopyIcon,
  RefreshCcwIcon,
} from "lucide-react";
import type { ChatStatus } from "ai";

// ---------------------------------------------------------------------------
// Attachments display (must be inside PromptInput)
// ---------------------------------------------------------------------------

function AttachmentsDisplay() {
  const attachments = usePromptInputAttachments();

  if (attachments.files.length === 0) return null;

  return (
    <Attachments variant="inline">
      {attachments.files.map((file) => (
        <Attachment
          data={file}
          key={file.id}
          onRemove={() => attachments.remove(file.id)}
        >
          <AttachmentPreview />
          <AttachmentRemove />
        </Attachment>
      ))}
    </Attachments>
  );
}

// ---------------------------------------------------------------------------
// Message item
// ---------------------------------------------------------------------------

function ChatMessageItem({
  message,
  isLast,
  onRetry,
}: {
  message: ChatMessage;
  isLast: boolean;
  onRetry?: () => void;
}) {
  return (
    <>
      <Message from={message.role}>
        <MessageContent>
          <MessageResponse isAnimating={message.isStreaming}>
            {message.content}
          </MessageResponse>
        </MessageContent>
      </Message>
      {message.role === "assistant" && isLast && !message.isStreaming && message.content && (
        <MessageActions>
          <MessageAction
            tooltip="Copy"
            label="Copy message"
            onClick={() => navigator.clipboard.writeText(message.content)}
          >
            <CopyIcon className="size-3" />
          </MessageAction>
          {onRetry && (
            <MessageAction tooltip="Retry" label="Retry" onClick={onRetry}>
              <RefreshCcwIcon className="size-3" />
            </MessageAction>
          )}
        </MessageActions>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Suggestions
// ---------------------------------------------------------------------------

const SUGGESTIONS = [
  "What did I work on today?",
  "Summarize my recent screen time",
  "What apps have I been using?",
  "Help me write a summary",
];

// ---------------------------------------------------------------------------
// ChatPage
// ---------------------------------------------------------------------------

export function ChatPage() {
  const {
    messages,
    isStreaming,
    sendMessage,
    stopStreaming,
    clearMessages,
  } = useChatStore();

  const [inputText, setInputText] = useState("");

  const chatStatus: ChatStatus = isStreaming ? "streaming" : "ready";

  const handleSubmit = useCallback(
    (message: PromptInputMessage) => {
      const text = message.text.trim();
      const hasFiles = message.files && message.files.length > 0;
      if ((!text && !hasFiles) || isStreaming) return;
      setInputText("");
      void sendMessage(text || "Sent with attachments");
    },
    [isStreaming, sendMessage],
  );

  const handleSuggestion = useCallback(
    (text: string) => {
      if (isStreaming) return;
      setInputText("");
      void sendMessage(text);
    },
    [isStreaming, sendMessage],
  );

  const handleRetry = useCallback(() => {
    const lastUserMsg = [...messages].reverse().find((m) => m.role === "user");
    if (lastUserMsg && !isStreaming) {
      void sendMessage(lastUserMsg.content);
    }
  }, [messages, isStreaming, sendMessage]);

  return (
    <div className="flex h-full flex-col min-w-0">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-border shrink-0">
        <h2 className="text-base font-semibold text-foreground">Chat</h2>
        {messages.length > 0 && (
          <button
            onClick={clearMessages}
            className="flex items-center justify-center h-7 w-7 rounded hover:bg-secondary text-muted-foreground hover:text-foreground transition-colors"
            title="Clear chat"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Messages */}
      <Conversation className="flex-1">
        <ConversationContent>
          {messages.length === 0 && !isStreaming && (
            <ConversationEmptyState
              title="Chat with Nooto"
              description="Ask anything about your day, your notes, or get help with tasks."
              icon={<SparklesIcon className="size-8 text-muted-foreground/60" />}
            />
          )}
          {messages.map((msg, i) => (
            <ChatMessageItem
              key={msg.id}
              message={msg}
              isLast={i === messages.length - 1}
              onRetry={handleRetry}
            />
          ))}
          {isStreaming && messages.at(-1)?.role === "user" && (
            <Message from="assistant">
              <MessageContent>
                <div className="flex items-center gap-2 text-muted-foreground">
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  <span className="text-sm">Thinking...</span>
                </div>
              </MessageContent>
            </Message>
          )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      {/* Suggestions (only when empty) */}
      {messages.length === 0 && !isStreaming && (
        <div className="shrink-0 px-5 pb-2">
          <Suggestions>
            {SUGGESTIONS.map((s) => (
              <Suggestion key={s} suggestion={s} onClick={handleSuggestion} />
            ))}
          </Suggestions>
        </div>
      )}

      {/* Input bar */}
      <div className="shrink-0 px-5 pb-5 pt-3">
        <PromptInput
          onSubmit={handleSubmit}
          className="w-full"
          accept="image/*,application/pdf,text/*"
          multiple
        >
          <PromptInputHeader>
            <AttachmentsDisplay />
          </PromptInputHeader>
          <PromptInputBody>
            <PromptInputTextarea
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder="Ask anything..."
              autoFocus
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
              onStop={stopStreaming}
              disabled={chatStatus === "ready" && !inputText.trim()}
            />
          </PromptInputFooter>
        </PromptInput>
      </div>
    </div>
  );
}
