import { useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Code2, Cpu, FolderOpen } from "lucide-react";
import {
  Conversation,
  ConversationContent,
  ConversationEmptyState,
  ConversationScrollButton,
} from "../../ai-elements/conversation";
import { useStickToBottomContext } from "use-stick-to-bottom";
import { Message, MessageContent } from "../../ai-elements/message";
import { Tool, ToolGroup, type ToolStatus } from "../../ai-elements/tool";
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
  usePromptInputAttachments,
  type PromptInputMessage,
} from "../../ai-elements/prompt-input";
import {
  Attachment,
  AttachmentPreview,
  AttachmentRemove,
  Attachments,
} from "../../ai-elements/attachments";
import { GenerativeMarkdown } from "../../generative-ui/GenerativeMarkdown";
import { useCodingAgent, type AttachedImage, type AgentEvent } from "@/hooks/useCodingAgent";
import { buildTurns, type Turn, type TextChunk, type ToolSlot, type ImageChunk } from "./buildTurns";
import { OPENROUTER_MODELS, DEFAULT_MODEL_ID, findModel } from "./openrouterModels";
import { AgentStatusStrip } from "./AgentStatusStrip";
import { useCodingAgentSessionsStore } from "./codingAgentSessionsStore";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { TerminalPane } from "./TerminalPane";

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
    status,
  } = useCodingAgent();

  // Folder is the active session's working directory. Lifted into the
  // sessions store so picking a session from the sidebar updates the pill,
  // and the choice survives app restart.
  const folder = useCodingAgentSessionsStore((s) => s.currentCwd);
  const setFolder = useCodingAgentSessionsStore((s) => s.setCurrentCwd);
  const currentFilePath = useCodingAgentSessionsStore((s) => s.currentFilePath);

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [inputText, setInputText] = useState("");
  // Track which session file we last loaded so the watcher below doesn't
  // re-spawn Pi every render or reload the same session twice in a row.
  const loadedFilePathRef = useRef<string | null>(null);
  const [model, setModelState] = useState<string>(() => {
    const stored = typeof window !== "undefined" ? localStorage.getItem(MODEL_STORAGE_KEY) : null;
    return stored && findModel(stored) ? stored : DEFAULT_MODEL_ID;
  });

  // Fetch the runtime mode (direct vs cloud) once on mount so we can swap the
  // model dropdown for a static badge when direct mode is active — the picker
  // is irrelevant there because the spawn always uses NOOTO_DIRECT_LLM_MODEL.
  const [modeInfo, setModeInfo] = useState<{ direct: boolean; directModel?: string }>({ direct: false });
  useEffect(() => {
    invoke<{ direct: boolean; directModel?: string }>("coding_agent_get_mode_info")
      .then(setModeInfo)
      .catch(() => {
        /* keep cloud-mode default */
      });
  }, []);

  const setModel = useCallback((next: string) => {
    setModelState(next);
    if (typeof window !== "undefined") localStorage.setItem(MODEL_STORAGE_KEY, next);
    // Force a fresh session on model change so the next prompt uses the new
    // model. Pi binds the model at sidecar spawn time, so we cannot live-swap.
    setSessionId(null);
  }, []);

  // Watch the sessions store for a session selection. When the sidebar picks
  // one, we — running inside the same hook instance the chat reads from —
  // call startSession with the file path. That triggers the JSONL replay so
  // the chat repopulates with the prior conversation.
  useEffect(() => {
    if (!currentFilePath || !folder) return;
    if (loadedFilePathRef.current === currentFilePath) return;
    loadedFilePathRef.current = currentFilePath;

    void (async () => {
      try {
        const id = await startSession(folder, "", model, currentFilePath);
        setSessionId(id);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        pushError(`Failed to load session: ${message}`);
      }
    })();
  }, [currentFilePath, folder, model, startSession, pushError]);

  const turns = buildTurns(events);

  const handlePickFolder = useCallback(async () => {
    const chosen = await pickFolder();
    if (chosen) setFolder(chosen);
    return chosen;
  }, [pickFolder]);

  const handleSubmit = useCallback(
    async (message: PromptInputMessage) => {
      const text = message.text.trim();
      const fileList = message.files ?? [];
      if (!text && fileList.length === 0) return;
      if (isStreaming) return;
      setInputText("");

      // Convert any attached images to base64 for Pi's RPC `images` field.
      // Filter to image MIME types — Pi only handles images today; PDFs would
      // need text extraction first.
      const imageFiles = fileList.filter((f) => f.mediaType?.startsWith("image/"));
      const skipped = fileList.length - imageFiles.length;
      if (skipped > 0) {
        pushError(`${skipped} non-image attachment ignored — only images are supported right now.`);
      }

      // Warn if the selected model can't actually use images.
      if (imageFiles.length > 0 && !modeInfo.direct) {
        const m = findModel(model);
        if (m && !m.vision) {
          pushError(`${m.name} doesn't accept images. Pick a vision-capable model (Claude / GPT-4o) or remove the attachment.`);
          return;
        }
      }

      let images: AttachedImage[] = [];
      try {
        images = await Promise.all(
          imageFiles.map(async (f) => ({
            data: await fileToBase64(f as unknown as File),
            mimeType: f.mediaType ?? "image/png",
          })),
        );
      } catch (err) {
        pushError(`Failed to read attached image: ${err instanceof Error ? err.message : String(err)}`);
        return;
      }

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
      pushUserText(text, images);

      try {
        if (!sessionId) {
          const id = await startSession(workingFolder, text, model, undefined, images);
          setSessionId(id);
        } else {
          await sendMessage(sessionId, text, images);
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        pushError(`Failed to send to coding agent: ${message}`);
      }
    },
    [folder, isStreaming, model, modeInfo.direct, pickFolder, pushError, pushUserText, sendMessage, sessionId, setFolder, startSession],
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
          <AutoScrollOnEvents events={events} />
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      <TerminalPane sessionId={sessionId} />
      <AgentStatusStrip status={status} onStop={handleStop} />
      <div className="shrink-0 px-5 pb-5 pt-3">
        <PromptInput
          onSubmit={handleSubmit}
          className="w-full"
          accept="image/*"
          multiple
        >
          <PromptInputBody>
            <AttachedImagesDisplay />
            <PromptInputTextarea
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder={
                folder
                  ? "Describe the change or task… (drop a screenshot to attach)"
                  : "Pick a folder, then describe the task…"
              }
              autoFocus
            />
          </PromptInputBody>
          <PromptInputFooter>
            <PromptInputTools>
              <PromptInputActionMenu>
                <PromptInputActionMenuTrigger />
                <PromptInputActionMenuContent>
                  <PromptInputActionAddAttachments label="Attach screenshot" />
                </PromptInputActionMenuContent>
              </PromptInputActionMenu>
              <FolderPickerButton folder={folder} onPick={() => void handlePickFolder()} />
              {modeInfo.direct ? (
                <DirectModeBadge model={modeInfo.directModel ?? "qwen3.6-35b-a3b"} />
              ) : (
                <ModelSelector value={model} onChange={setModel} />
              )}
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

/**
 * Force StickToBottom to scroll on every events change. Streaming text deltas
 * sometimes don't trip the library's ResizeObserver fast enough to keep the
 * tail visible. Mounting this inside <ConversationContent> gives it access to
 * the StickToBottom context.
 */
function AutoScrollOnEvents({ events }: { events: AgentEvent[] }) {
  const { scrollToBottom, isAtBottom } = useStickToBottomContext();
  // Hash recent text length so streaming deltas re-trigger the effect even
  // when events.length doesn't change (the last assistant turn grows).
  const tailKey = events.length === 0
    ? "empty"
    : `${events.length}:${eventTailLength(events[events.length - 1])}`;

  useEffect(() => {
    if (isAtBottom) {
      scrollToBottom();
    }
  }, [tailKey, isAtBottom, scrollToBottom]);
  return null;
}

function eventTailLength(ev: AgentEvent | undefined): number {
  if (!ev) return 0;
  if (ev.type === "text" || ev.type === "user_text") return ev.text.length;
  if (ev.type === "tool_result") return ev.output.length;
  return 0;
}

/**
 * Renders the in-prompt preview of attachments the user has staged. Must be a
 * descendant of `<PromptInput>` because `usePromptInputAttachments()` reads
 * from a context that PromptInput provides.
 */
function AttachedImagesDisplay() {
  const attachments = usePromptInputAttachments();
  if (attachments.files.length === 0) return null;
  return (
    <Attachments variant="inline">
      {attachments.files.map((file) => (
        <Attachment data={file} key={file.id} onRemove={() => attachments.remove(file.id)}>
          <AttachmentPreview />
          <AttachmentRemove />
        </Attachment>
      ))}
    </Attachments>
  );
}

/**
 * Read a File into a raw base64 string (no `data:image/...;base64,` prefix).
 * Pi expects raw base64 in the `images[].data` field.
 */
async function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== "string") {
        reject(new Error("FileReader returned non-string"));
        return;
      }
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () => reject(reader.error ?? new Error("FileReader failed"));
    reader.readAsDataURL(file);
  });
}

function DirectModeBadge({ model }: { model: string }) {
  return (
    <div
      className="flex items-center gap-1.5 rounded-md bg-emerald-500/10 px-2.5 py-1 text-xs text-emerald-600 dark:text-emerald-400"
      title={`Direct mode — calling ${model} on your local vLLM (NOOTO_DIRECT_LLM_URL)`}
    >
      <Cpu className="size-3.5" />
      <span className="font-mono">{model} · local</span>
    </div>
  );
}

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
    const images = turn.items.filter((i): i is ImageChunk => i.kind === "image");
    return (
      <Message from="user">
        <MessageContent>
          {images.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-2">
              {images.map((img) => (
                <img
                  key={img.id}
                  src={`data:${img.mimeType};base64,${img.data}`}
                  alt="attachment"
                  className="max-h-48 max-w-xs rounded-lg border border-border object-cover"
                />
              ))}
            </div>
          )}
          {text && <p className="whitespace-pre-wrap">{text}</p>}
        </MessageContent>
      </Message>
    );
  }

  // Bunch consecutive tool calls into a ToolGroup so the chat doesn't show
  // five separate cards for "agent did 5 reads in a row".
  const blocks: React.ReactNode[] = [];
  let i = 0;
  while (i < turn.items.length) {
    const item = turn.items[i]!;
    if (item.kind === "tool") {
      const tools: ToolSlot[] = [];
      while (i < turn.items.length && turn.items[i]!.kind === "tool") {
        tools.push(turn.items[i] as ToolSlot);
        i++;
      }
      blocks.push(
        <ToolGroup key={`tg-${tools[0]!.call.id}`} className="my-2">
          {tools.map((t) => (
            <ToolCallView key={t.call.id} slot={t} />
          ))}
        </ToolGroup>,
      );
      continue;
    }
    if (item.kind === "text") {
      const isLast = i === turn.items.length - 1;
      blocks.push(
        <GenerativeMarkdown
          key={item.id}
          content={item.text}
          isAnimating={isStreaming && isLast}
        />,
      );
    } else if (item.kind === "error") {
      blocks.push(
        <p key={item.id} className="text-sm text-destructive">
          {item.message}
        </p>,
      );
    }
    i++;
  }

  return (
    <Message from="assistant">
      <MessageContent>{blocks}</MessageContent>
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
      // Drop the default my-2 — ToolGroup controls spacing between siblings.
      className="my-0"
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


function safeStringify(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
