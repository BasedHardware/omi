import { useCallback, useEffect, useRef, useState } from "react";
import {
  FolderOpen,
  Send,
  Square,
  AlertCircle,
  Code2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useCodingAgent } from "@/hooks/useCodingAgent";
import { ToolCallBubble } from "./ToolCallBubble";
import { ModelMessage } from "./ModelMessage";
import { cn } from "@/lib/utils";
import { buildTurns, type Turn, type TextChunk } from "./buildTurns";

// ---------------------------------------------------------------------------
// CodingAgentSession
// ---------------------------------------------------------------------------

export function CodingAgentSession() {
  const { pickFolder, startSession, sendMessage, stopSession, events, isStreaming } =
    useCodingAgent();

  const [folder, setFolder] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [input, setInput] = useState("");

  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom whenever events arrive.
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events]);

  const handlePickFolder = useCallback(async () => {
    const chosen = await pickFolder();
    if (chosen) setFolder(chosen);
  }, [pickFolder]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput("");

    if (!folder) {
      const chosen = await pickFolder();
      if (!chosen) return;
      setFolder(chosen);
      const id = await startSession(chosen, text);
      setSessionId(id);
    } else if (!sessionId) {
      const id = await startSession(folder, text);
      setSessionId(id);
    } else {
      await sendMessage(sessionId, text);
    }
  }, [input, isStreaming, folder, sessionId, pickFolder, startSession, sendMessage]);

  const handleStop = useCallback(async () => {
    if (sessionId) {
      await stopSession(sessionId);
      setSessionId(null);
    }
  }, [sessionId, stopSession]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      void handleSend();
    }
  };

  const turns = buildTurns(events);

  return (
    <div className="flex h-full flex-col min-w-0">
      {/* Message list */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-5 py-4 space-y-4 min-h-0"
      >
        {turns.length === 0 && !isStreaming && (
          <div className="flex flex-col items-center justify-center h-full gap-4 text-center py-16">
            <div className="flex size-14 items-center justify-center rounded-2xl bg-primary/10">
              <Code2 className="size-6 text-primary" />
            </div>
            <div className="space-y-1.5 max-w-sm">
              <p className="text-base font-semibold text-foreground">Coding Agent</p>
              <p className="text-sm text-muted-foreground">
                {folder
                  ? "Describe what you want to build or fix. The agent reads, edits, and runs code in your folder."
                  : "Pick a project folder to get started. The agent reads, edits, and runs code on your machine."}
              </p>
            </div>
            {!folder && (
              <Button
                size="sm"
                onClick={() => void handlePickFolder()}
                className="gap-1.5"
              >
                <FolderOpen className="size-3.5" />
                Pick folder
              </Button>
            )}
            {folder && (
              <div className="flex items-center gap-1.5 rounded-md bg-primary/10 px-2.5 py-1 text-xs font-mono text-primary">
                <FolderOpen className="size-3.5" />
                <span className="max-w-[280px] truncate">{folder.split("/").pop()}</span>
              </div>
            )}
          </div>
        )}

        {turns.map((turn) => (
          <TurnRow key={turn.id} turn={turn} isStreaming={isStreaming && turn.isOpen} />
        ))}
      </div>

      {/* Input row */}
      <div className="shrink-0 px-5 pb-5 pt-3 border-t border-border">
        <div className="flex flex-col gap-2 rounded-xl border bg-card p-3">
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              folder
                ? "Describe the change or task… (⌘↵ to send)"
                : "Pick a folder and describe the task… (⌘↵ to send)"
            }
            rows={3}
            className="resize-none border-0 bg-transparent p-0 text-sm shadow-none focus-visible:ring-0 placeholder:text-muted-foreground/60"
          />
          <div className="flex items-center justify-between gap-2">
            {/* Folder pill */}
            <button
              onClick={() => void handlePickFolder()}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs transition-colors",
                folder
                  ? "bg-muted text-muted-foreground hover:bg-accent/70 hover:text-foreground"
                  : "border border-dashed border-border text-muted-foreground hover:border-primary/50 hover:text-foreground",
              )}
              title={folder ?? "Pick a project folder"}
            >
              <FolderOpen className="size-3.5" />
              <span className="max-w-[200px] truncate font-mono">
                {folder ? folder.split("/").pop() : "Pick folder"}
              </span>
            </button>

            <div className="flex items-center gap-2">
              {isStreaming && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => void handleStop()}
                  className="h-7 gap-1.5 text-xs text-muted-foreground"
                >
                  <Square className="size-3" />
                  Stop
                </Button>
              )}
              <Button
                size="sm"
                className="h-7 gap-1.5 text-xs"
                disabled={!input.trim() || isStreaming}
                onClick={() => void handleSend()}
              >
                <Send className="size-3" />
                Send
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function TurnRow({ turn, isStreaming }: { turn: Turn; isStreaming: boolean }) {
  if (turn.role === "user") {
    const text =
      turn.items
        .filter((i): i is TextChunk => i.kind === "text")
        .map((i) => i.text)
        .join("") ?? "";
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground">
          {text}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {turn.items.map((item, i) => {
        if (item.kind === "text") {
          return (
            <ModelMessage
              key={item.id}
              text={item.text}
              isStreaming={isStreaming && i === turn.items.length - 1}
            />
          );
        }
        if (item.kind === "tool") {
          return (
            <ToolCallBubble key={item.call.id} call={item.call} result={item.result} />
          );
        }
        if (item.kind === "error") {
          return (
            <Alert key={item.id} variant="destructive" className="text-sm">
              <AlertCircle className="size-4" />
              <AlertTitle>Agent error</AlertTitle>
              <AlertDescription>{item.message}</AlertDescription>
            </Alert>
          );
        }
        return null;
      })}
    </div>
  );
}
