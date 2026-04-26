/**
 * Meeting chat sidebar — ask questions about a specific recorded meeting.
 *
 * Messages are scoped per conversation.id in an in-memory map so switching
 * meetings preserves each thread for the app session (cleared on reload).
 * Streaming reuses the main chat's Claude/Gemini pipeline, but with a
 * meeting-scoped system prompt (title, overview, app insights, transcript)
 * instead of the global goals/tasks/memories snapshot.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import { X, SparklesIcon, SendIcon, Loader2 } from "lucide-react";
import { nanoid } from "nanoid";

import { Button } from "../ui/button";
import type { Conversation } from "../../stores/conversationStore";
import { useClaudeStore } from "@/stores/claudeStore";
import { createClient, sendMessageStreaming } from "@/services/chat";
import { api } from "@/services/api";
import { GenerativeMarkdown } from "../generative-ui";
import { Message, MessageContent } from "../ai-elements/message";
import { Suggestion, Suggestions } from "../ai-elements/suggestion";

const SIDEBAR_WIDTH = 400;

interface MeetingMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
}

const threads = new Map<string, MeetingMessage[]>();

function getThread(id: string): MeetingMessage[] {
  return threads.get(id) ?? [];
}

function buildMeetingSystemPrompt(conversation: Conversation): string {
  const title = conversation.structured?.title || "Untitled Meeting";
  const overview = conversation.structured?.overview || "";
  const category = conversation.structured?.category || "";
  const segments = conversation.transcript_segments ?? [];
  const apps = conversation.apps_results ?? [];
  const startedAt = conversation.started_at || conversation.created_at;

  const sections: string[] = [
    "You are Nooto, helping the user understand and act on a specific recorded meeting.",
    "Answer using only the meeting data below unless the user explicitly asks you to search elsewhere or take an action.",
    "If a question can't be answered from the meeting, say so. Quote the transcript when it supports your answer. Be concise.",
    "",
    "<meeting_metadata>",
    `Title: ${title}`,
  ];
  if (category) sections.push(`Category: ${category}`);
  if (startedAt) sections.push(`Recorded: ${new Date(startedAt).toLocaleString()}`);
  sections.push("</meeting_metadata>");

  if (overview) {
    sections.push("", "<meeting_overview>", overview, "</meeting_overview>");
  }

  if (apps.length > 0) {
    sections.push("", "<app_insights>");
    for (const a of apps) {
      const label = a.app_id ? `App: ${a.app_id}` : `App #${a.id}`;
      sections.push(`--- ${label} ---`, a.content ?? "");
    }
    sections.push("</app_insights>");
  }

  if (segments.length > 0) {
    sections.push("", "<meeting_transcript>");
    for (const seg of segments) {
      const speaker = seg.speaker || "UNKNOWN";
      sections.push(`${speaker}: ${seg.text}`);
    }
    sections.push("</meeting_transcript>");
  } else {
    sections.push("", "<meeting_transcript>(no transcript available)</meeting_transcript>");
  }

  return sections.join("\n");
}

function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

const SUGGESTIONS = [
  "Summarize the key points",
  "What decisions were made?",
  "List action items",
  "Who said what about the main topic?",
];

export function MeetingChatSidebar({
  conversation,
  onClose,
}: {
  conversation: Conversation;
  onClose: () => void;
}) {
  const conversationId = conversation.id;
  const [messages, setMessages] = useState<MeetingMessage[]>(() =>
    getThread(conversationId),
  );
  const [inputText, setInputText] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);

  // Tracks which conversation the rendered `messages` belongs to. Streaming
  // callbacks close over the sending conversationId; if the user switches
  // meetings mid-stream, we still need to update the module map for that
  // original thread but must NOT push those messages into the visible state.
  const activeIdRef = useRef(conversationId);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    activeIdRef.current = conversationId;
    setMessages(getThread(conversationId));
    setInputText("");
  }, [conversationId]);

  // Only stick to bottom when the user was already near it — don't yank them
  // away from earlier content they scrolled up to read.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distanceFromBottom < 80) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages]);

  const writeThread = useCallback((id: string, next: MeetingMessage[]) => {
    threads.set(id, next);
    if (activeIdRef.current === id) {
      setMessages(next);
    }
  }, []);

  const handleSend = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isStreaming) return;

      const targetId = conversationId;
      const userMsg: MeetingMessage = {
        id: nanoid(),
        role: "user",
        content: trimmed,
      };
      const assistantId = nanoid();
      const assistantMsg: MeetingMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        isStreaming: true,
      };

      const base = getThread(targetId);
      writeThread(targetId, [...base, userMsg, assistantMsg]);
      setInputText("");
      setIsStreaming(true);

      const appendDelta = (delta: string) => {
        const cur = getThread(targetId).map((m) =>
          m.id === assistantId ? { ...m, content: m.content + delta } : m,
        );
        writeThread(targetId, cur);
      };

      const history = base
        .filter((m) => m.content.trim() !== "")
        .slice(-20)
        .map((m) => ({ role: m.role, content: m.content }));

      const systemPrompt = buildMeetingSystemPrompt(conversation);
      const claudeToken = useClaudeStore.getState().accessToken;

      try {
        if (claudeToken) {
          const client = createClient(claudeToken);
          const claudeMessages = [
            ...history.map((h) => ({
              role: h.role as "user" | "assistant",
              content: h.content,
            })),
            { role: "user" as const, content: trimmed },
          ];
          await sendMessageStreaming(client, claudeMessages, systemPrompt, appendDelta);
        } else {
          await api.sendChatViaGemini(trimmed, appendDelta, history, systemPrompt);
        }

        const done = getThread(targetId).map((m) =>
          m.id === assistantId ? { ...m, isStreaming: false } : m,
        );
        writeThread(targetId, done);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        const aborted = isAbortError(err);
        const cur = getThread(targetId).map((m) => {
          if (m.id !== assistantId) return m;
          const suffix = !aborted && m.content === "" ? `*Error: ${message}*` : "";
          return { ...m, content: m.content + suffix, isStreaming: false };
        });
        writeThread(targetId, cur);
        if (!aborted) console.error("[MeetingChat] send failed", err);
      } finally {
        if (activeIdRef.current === targetId) {
          setIsStreaming(false);
        }
      }
    },
    [conversation, conversationId, isStreaming, writeThread],
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend(inputText);
    }
  };

  return (
    <motion.aside
      className="flex shrink-0 flex-col overflow-hidden border-l border-border/50 bg-background"
      initial={{ width: 0, opacity: 0 }}
      animate={{ width: SIDEBAR_WIDTH, opacity: 1 }}
      exit={{ width: 0, opacity: 0 }}
      transition={{ duration: 0.24, ease: [0.4, 0, 0.2, 1] }}
    >
      <div className="flex h-full flex-col" style={{ width: SIDEBAR_WIDTH }}>
        <div className="flex items-center justify-between border-b border-border/50 px-4 py-3">
          <div className="flex items-center gap-2">
            <SparklesIcon className="size-3.5 text-muted-foreground" />
            <h4 className="text-sm font-semibold text-foreground">Ask about this meeting</h4>
          </div>
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={onClose}
            aria-label="Close meeting chat"
          >
            <X className="size-3.5" />
          </Button>
        </div>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-3">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-4 px-4 text-center">
              <SparklesIcon className="size-8 text-muted-foreground/60" />
              <div className="space-y-1">
                <p className="text-sm font-medium text-foreground">
                  Chat with this meeting
                </p>
                <p className="text-xs text-muted-foreground">
                  Ask questions, extract action items, or get a focused summary.
                </p>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {messages.map((m) => (
                <MeetingChatMessage key={m.id} message={m} />
              ))}
            </div>
          )}
        </div>

        {messages.length === 0 && !isStreaming && (
          <div className="shrink-0 px-3 pb-2">
            <Suggestions>
              {SUGGESTIONS.map((s) => (
                <Suggestion key={s} suggestion={s} onClick={handleSend} />
              ))}
            </Suggestions>
          </div>
        )}

        <div className="shrink-0 border-t border-border/50 px-3 py-3">
          <div className="flex items-end gap-2 rounded-lg border border-border bg-background px-3 py-2 focus-within:border-ring">
            <textarea
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about this meeting…"
              rows={1}
              className="flex-1 resize-none bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none max-h-32"
            />
            <Button
              size="icon-xs"
              variant="ghost"
              onClick={() => void handleSend(inputText)}
              disabled={!inputText.trim() || isStreaming}
              aria-label="Send"
            >
              {isStreaming ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <SendIcon className="size-3.5" />
              )}
            </Button>
          </div>
        </div>
      </div>
    </motion.aside>
  );
}

function MeetingChatMessage({ message }: { message: MeetingMessage }) {
  return (
    <Message from={message.role}>
      <MessageContent>
        {message.role === "user" ? (
          <div className="whitespace-pre-wrap">{message.content}</div>
        ) : message.content ? (
          <GenerativeMarkdown
            content={message.content}
            isAnimating={message.isStreaming}
          />
        ) : (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" />
            <span className="text-xs">Thinking…</span>
          </div>
        )}
      </MessageContent>
    </Message>
  );
}
