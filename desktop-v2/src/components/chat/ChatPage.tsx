/**
 * Chat page — AI chat via Gemini.
 *
 * Layout: two-column flex. Left column is the ChatSessionsSidebar listing
 * prior sessions; right column is the familiar messages + input area.
 *
 * Calls Gemini directly for streaming responses. Local screen capture data
 * is automatically injected as context when the user asks about their
 * activity. Messages + sessions are persisted locally via
 * tauri-plugin-store.
 */

import { useCallback, useState } from "react";
import { useChatStore } from "../../stores/chatStore";
import type { ChatMessage, Citation } from "../../stores/chatStore";
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
} from "../ai-elements/message";
import { ContextUsage } from "../ai-elements/context";
import { MessageParts } from "./MessageParts";
import { ModelSelector } from "./ModelSelector";
import {
  PromptInput,
  PromptInputBody,
  PromptInputTextarea,
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
  ListPlus,
} from "lucide-react";
import type { ChatStatus } from "ai";
import { CitationList } from "./CitationList";
import { ChatSessionsSidebar } from "./ChatSessionsSidebar";
import { TaskChatPanel } from "./TaskChatPanel";
import { CodingAgentSession } from "./coding-agent/CodingAgentSession";
import { CODING_AGENT_ENABLED } from "@/config/codingAgentFeatureFlag";
import { cn } from "@/lib/utils";

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
  taskPanelOpen,
  onToggleTaskPanel,
  onCitationSelect,
}: {
  message: ChatMessage;
  isLast: boolean;
  onRetry?: () => void;
  taskPanelOpen: boolean;
  onToggleTaskPanel: () => void;
  onCitationSelect: (c: Citation) => void;
}) {
  const showActions =
    message.role === "assistant" && !message.isStreaming && message.content;

  return (
    <>
      <Message from={message.role}>
        <MessageContent>
          <MessageParts message={message} />
          {message.role === "assistant" &&
            message.citations &&
            message.citations.length > 0 && (
              <CitationList
                citations={message.citations}
                onSelect={onCitationSelect}
              />
            )}
        </MessageContent>
      </Message>
      {showActions && (
        <MessageActions>
          <MessageAction
            tooltip="Copy"
            label="Copy message"
            onClick={() => navigator.clipboard.writeText(message.content)}
          >
            <CopyIcon className="size-3" />
          </MessageAction>
          {isLast && onRetry && (
            <MessageAction tooltip="Retry" label="Retry" onClick={onRetry}>
              <RefreshCcwIcon className="size-3" />
            </MessageAction>
          )}
          <MessageAction
            tooltip={taskPanelOpen ? "Close task panel" : "Save as task"}
            label="Save as task"
            onClick={onToggleTaskPanel}
          >
            <ListPlus className="size-3" />
          </MessageAction>
        </MessageActions>
      )}
      {taskPanelOpen && (
        <div className="chat-task-panel-wrapper">
          <TaskChatPanel
            suggestion={message.content}
            sourceMessageId={message.id}
            onClose={onToggleTaskPanel}
          />
        </div>
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

/**
 * Rough soft cap for session context display — ~200k tokens worth of chars
 * (Gemini 2.5 Flash supports ~1M tokens). This is an indicator, not a hard
 * limit; the actual window is determined by the model + history-slicing in
 * `chatStore.ts`.
 */
const CONTEXT_SOFT_CAP = 800_000;

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
  const [taskPanelMessageId, setTaskPanelMessageId] = useState<string | null>(null);
  const [mode, setMode] = useState<"chat" | "code">(() => {
    const stored = typeof window !== "undefined" ? sessionStorage.getItem("chat:mode") : null;
    return stored === "code" && CODING_AGENT_ENABLED ? "code" : "chat";
  });

  const setModeAndPersist = useCallback((next: "chat" | "code") => {
    setMode(next);
    if (typeof window !== "undefined") sessionStorage.setItem("chat:mode", next);
  }, []);

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

  const handleToggleTaskPanel = useCallback((id: string) => {
    setTaskPanelMessageId((cur) => (cur === id ? null : id));
  }, []);

  const handleCitationSelect = useCallback((_c: Citation) => {
    // Navigation hook — consumers wire it here.
  }, []);

  return (
    <div className="flex h-full min-w-0 flex-col">
      {CODING_AGENT_ENABLED && <ChatModeTabs mode={mode} onChange={setModeAndPersist} />}
      {mode === "code" ? (
        <div className="flex flex-1 min-h-0">
          <CodingAgentSession />
        </div>
      ) : (
        <ChatModeBody
          messages={messages}
          isStreaming={isStreaming}
          sendMessage={sendMessage}
          stopStreaming={stopStreaming}
          clearMessages={clearMessages}
          inputText={inputText}
          setInputText={setInputText}
          taskPanelMessageId={taskPanelMessageId}
          handleSubmit={handleSubmit}
          handleSuggestion={handleSuggestion}
          handleRetry={handleRetry}
          handleToggleTaskPanel={handleToggleTaskPanel}
          handleCitationSelect={handleCitationSelect}
          chatStatus={chatStatus}
        />
      )}
    </div>
  );
}

function ChatModeTabs({
  mode,
  onChange,
}: {
  mode: "chat" | "code";
  onChange: (m: "chat" | "code") => void;
}) {
  return (
    <div className="flex items-center gap-1 border-b border-border px-5 py-2 shrink-0">
      {(["chat", "code"] as const).map((m) => (
        <button
          key={m}
          onClick={() => onChange(m)}
          className={cn(
            "rounded-md px-3 py-1 text-xs font-medium transition-colors",
            mode === m
              ? "bg-secondary text-foreground"
              : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
          )}
        >
          {m === "chat" ? "Chat" : "Code"}
        </button>
      ))}
    </div>
  );
}

interface ChatModeBodyProps {
  messages: ChatMessage[];
  isStreaming: boolean;
  sendMessage: (text: string) => void | Promise<void>;
  stopStreaming: () => void;
  clearMessages: () => void;
  inputText: string;
  setInputText: (s: string) => void;
  taskPanelMessageId: string | null;
  handleSubmit: (m: PromptInputMessage) => void;
  handleSuggestion: (s: string) => void;
  handleRetry: () => void;
  handleToggleTaskPanel: (id: string) => void;
  handleCitationSelect: (c: Citation) => void;
  chatStatus: ChatStatus;
}

function ChatModeBody({
  messages,
  isStreaming,
  stopStreaming,
  clearMessages,
  inputText,
  setInputText,
  taskPanelMessageId,
  handleSubmit,
  handleSuggestion,
  handleRetry,
  handleToggleTaskPanel,
  handleCitationSelect,
  chatStatus,
}: ChatModeBodyProps) {
  return (
    <div className="flex flex-1 min-h-0 min-w-0 flex-row">
      {/* Sessions rail */}
      <ChatSessionsSidebar />

      {/* Main chat column */}
      <div className="flex h-full flex-1 min-w-0 flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-border shrink-0">
          <h2 className="text-base font-semibold text-foreground">Chat</h2>
          <div className="flex items-center gap-3">
            {messages.length > 0 && (
              <ContextUsage
                used={messages.reduce((n, m) => n + m.content.length, 0)}
                max={CONTEXT_SOFT_CAP}
              />
            )}
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
                taskPanelOpen={taskPanelMessageId === msg.id}
                onToggleTaskPanel={() => handleToggleTaskPanel(msg.id)}
                onCitationSelect={handleCitationSelect}
              />
            ))}
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
            <PromptInputBody>
              <AttachmentsDisplay />
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
                <ModelSelector />
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
    </div>
  );
}
