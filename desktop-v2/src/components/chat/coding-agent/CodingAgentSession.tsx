import { useCallback, useState } from "react";
import { Code2, FolderOpen } from "lucide-react";
import {
  Conversation,
  ConversationContent,
  ConversationEmptyState,
  ConversationScrollButton,
} from "../../ai-elements/conversation";
import { Message, MessageContent } from "../../ai-elements/message";
import { Tool, type ToolStatus } from "../../ai-elements/tool";
import {
  PromptInput,
  PromptInputBody,
  PromptInputTextarea,
  PromptInputFooter,
  PromptInputTools,
  PromptInputSubmit,
  type PromptInputMessage,
} from "../../ai-elements/prompt-input";
import { GenerativeMarkdown } from "../../generative-ui/GenerativeMarkdown";
import { useCodingAgent } from "@/hooks/useCodingAgent";
import { buildTurns, type Turn, type TextChunk, type ToolSlot } from "./buildTurns";
import { OPENROUTER_MODELS, DEFAULT_MODEL_ID, findModel } from "./openrouterModels";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

const MODEL_STORAGE_KEY = "coding-agent:model";

// ---------------------------------------------------------------------------
// CodingAgentSession — coding-agent surface inside the /chat page (Code mode).
//
// Mirrors ChatPage's primitives (Conversation / Message / Tool / PromptInput)
// so the look + interactions match the regular chat exactly.
// ---------------------------------------------------------------------------

export function CodingAgentSession() {
  const {
    pickFolder,
    startSession,
    sendMessage,
    stopSession,
    pushUserText,
    pushError,
    events,
    isStreaming,
  } = useCodingAgent();

  const [folder, setFolder] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [inputText, setInputText] = useState("");
  const [model, setModelState] = useState<string>(() => {
    const stored = typeof window !== "undefined" ? localStorage.getItem(MODEL_STORAGE_KEY) : null;
    return stored && findModel(stored) ? stored : DEFAULT_MODEL_ID;
  });

  const setModel = useCallback((next: string) => {
    setModelState(next);
    if (typeof window !== "undefined") localStorage.setItem(MODEL_STORAGE_KEY, next);
    // Force a fresh session on model change so the next prompt uses the new
    // model. Pi binds the model at sidecar spawn time, so we cannot live-swap.
    setSessionId(null);
  }, []);

  const turns = buildTurns(events);

  const handlePickFolder = useCallback(async () => {
    const chosen = await pickFolder();
    if (chosen) setFolder(chosen);
    return chosen;
  }, [pickFolder]);

  const handleSubmit = useCallback(
    async (message: PromptInputMessage) => {
      const text = message.text.trim();
      if (!text || isStreaming) return;
      setInputText("");

      let workingFolder = folder;
      if (!workingFolder) {
        workingFolder = (await pickFolder()) ?? null;
        if (!workingFolder) {
          pushError("Pick a project folder before sending a prompt.");
          return;
        }
        setFolder(workingFolder);
      }

      // Show the user's prompt immediately so the chat doesn't sit empty
      // while the sidecar is starting up.
      pushUserText(text);

      try {
        if (!sessionId) {
          const id = await startSession(workingFolder, text, model);
          setSessionId(id);
        } else {
          await sendMessage(sessionId, text);
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        pushError(`Failed to send to coding agent: ${message}`);
      }
    },
    [folder, isStreaming, model, pickFolder, pushError, pushUserText, sendMessage, sessionId, startSession],
  );

  const handleStop = useCallback(() => {
    if (sessionId) {
      void stopSession(sessionId);
      setSessionId(null);
    }
  }, [sessionId, stopSession]);

  return (
    <div className="flex h-full min-w-0 flex-col">
      <Conversation className="flex-1">
        <ConversationContent>
          {turns.length === 0 && !isStreaming && (
            <ConversationEmptyState
              icon={
                <div className="flex size-14 items-center justify-center rounded-2xl bg-primary/10">
                  <Code2 className="size-6 text-primary" />
                </div>
              }
              title="Coding Agent"
              description={
                folder
                  ? "Describe what you want to build or fix. The agent reads, edits, and runs code in your folder."
                  : "Pick a project folder to get started. The agent reads, edits, and runs code on your machine."
              }
            />
          )}

          {turns.map((turn) => (
            <TurnView key={turn.id} turn={turn} isStreaming={isStreaming && turn.isOpen} />
          ))}

          {/* Thinking indicator — shown while a turn is in flight but the
              assistant hasn't produced any visible output yet. Without this,
              long cold starts (5-10s on OpenRouter Parasail routing) look
              like a hung session. */}
          {isStreaming && !hasOpenAssistantTurn(turns) && (
            <Message from="assistant">
              <MessageContent>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <span className="size-3.5 animate-spin rounded-full border-2 border-muted-foreground/40 border-t-foreground" />
                  Thinking…
                </div>
              </MessageContent>
            </Message>
          )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      <div className="shrink-0 px-5 pb-5 pt-3">
        <PromptInput onSubmit={handleSubmit} className="w-full">
          <PromptInputBody>
            <PromptInputTextarea
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder={
                folder
                  ? "Describe the change or task…"
                  : "Pick a folder, then describe the task…"
              }
              autoFocus
            />
          </PromptInputBody>
          <PromptInputFooter>
            <PromptInputTools>
              <FolderPickerButton folder={folder} onPick={() => void handlePickFolder()} />
              <ModelSelector value={model} onChange={setModel} />
            </PromptInputTools>
            <PromptInputSubmit
              status={isStreaming ? "streaming" : "ready"}
              onStop={handleStop}
              disabled={!isStreaming && !inputText.trim()}
            />
          </PromptInputFooter>
        </PromptInput>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------

function ModelSelector({
  value,
  onChange,
}: {
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="h-7 gap-1.5 border-dashed text-xs px-2.5 py-1 [&>svg]:size-3">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {OPENROUTER_MODELS.map((m) => (
          <SelectItem key={m.id} value={m.id}>
            <span className="text-xs">{m.name}</span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function FolderPickerButton({
  folder,
  onPick,
}: {
  folder: string | null;
  onPick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onPick}
      title={folder ?? "Pick a project folder"}
      className={cn(
        "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs transition-colors",
        folder
          ? "bg-muted text-muted-foreground hover:bg-accent/70 hover:text-foreground"
          : "border border-dashed border-border text-muted-foreground hover:border-primary/50 hover:text-foreground",
      )}
    >
      <FolderOpen className="size-3.5" />
      <span className="max-w-[220px] truncate font-mono">
        {folder ? folder.split("/").pop() : "Pick folder"}
      </span>
    </button>
  );
}

// ---------------------------------------------------------------------------

function TurnView({ turn, isStreaming }: { turn: Turn; isStreaming: boolean }) {
  if (turn.role === "user") {
    const text = turn.items
      .filter((i): i is TextChunk => i.kind === "text")
      .map((i) => i.text)
      .join("");
    return (
      <Message from="user">
        <MessageContent>
          <p className="whitespace-pre-wrap">{text}</p>
        </MessageContent>
      </Message>
    );
  }

  return (
    <Message from="assistant">
      <MessageContent>
        {turn.items.map((item, i) => {
          if (item.kind === "text") {
            const isLast = i === turn.items.length - 1;
            return (
              <GenerativeMarkdown
                key={item.id}
                content={item.text}
                isAnimating={isStreaming && isLast}
              />
            );
          }
          if (item.kind === "tool") {
            return <ToolCallView key={item.call.id} slot={item} />;
          }
          if (item.kind === "error") {
            return (
              <p key={item.id} className="text-sm text-destructive">
                {item.message}
              </p>
            );
          }
          return null;
        })}
      </MessageContent>
    </Message>
  );
}

// ---------------------------------------------------------------------------

function ToolCallView({ slot }: { slot: ToolSlot }) {
  const { call, result } = slot;
  const status: ToolStatus = result?.isError
    ? "error"
    : result !== undefined
    ? "completed"
    : "running";

  const inputStr = call.input != null ? safeStringify(call.input) : undefined;
  const output = result && !result.isError ? result.output : undefined;
  const errorMessage = result?.isError ? result.output : undefined;

  return (
    <Tool
      name={call.tool}
      status={status}
      input={inputStr}
      output={output}
      errorMessage={errorMessage}
      runningLabel={runningLabelFor(call.tool)}
    />
  );
}

function runningLabelFor(tool: string): string {
  switch (tool) {
    case "read":
      return "Reading file";
    case "write":
      return "Writing file";
    case "edit":
      return "Editing file";
    case "bash":
      return "Running command";
    case "grep":
      return "Searching";
    case "find":
      return "Finding files";
    case "ls":
      return "Listing directory";
    case "td":
      return "Querying td";
    default:
      return `Running ${tool}`;
  }
}

function hasOpenAssistantTurn(turns: Turn[]): boolean {
  const last = turns[turns.length - 1];
  return Boolean(last && last.role === "assistant" && last.items.length > 0);
}

function safeStringify(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
