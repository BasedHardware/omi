import { useEffect, useMemo, useState } from "react";
import { useConversationStore } from "../../stores/conversationStore";
import type { Conversation, TranscriptSegment } from "../../stores/conversationStore";
import { useAudioStore, type LiveSegment, TRANSCRIPTION_LANGUAGES } from "../../stores/audioStore";
import { Star, Search, Clock, User, CalendarIcon, X, StarIcon, Mic, MicOff, Loader2, Square, AlertTriangle, FileText } from "lucide-react";
import { format, isWithinInterval, startOfDay, endOfDay } from "date-fns";
import type { DateRange } from "react-day-picker";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { Tabs, TabsList, TabsTrigger } from "../ui/tabs";
import { Calendar } from "../ui/calendar";
import { type PersonaState } from "../ai-elements/persona";
import {
  Conversation as LiveConversation,
  ConversationContent as LiveConversationContent,
  ConversationScrollButton as LiveConversationScrollButton,
} from "../ai-elements/conversation";
import { Message, MessageContent } from "../ai-elements/message";
import { cn } from "@/lib/utils";
import { AnimatePresence, motion } from "motion/react";
import { AppInsightsEmpty, AppResultsFull } from "./AppResultsSection";
import { useAppStore } from "../../stores/appStore";

function audioStateToPersona(args: {
  audioEnabled: boolean;
  isRecording: boolean;
  inCommercialHours: boolean;
  isProcessing: boolean;
}): PersonaState {
  if (args.isProcessing) return "thinking";
  if (args.isRecording) return "listening";
  if (!args.audioEnabled) return "asleep";
  if (!args.inCommercialHours) return "asleep";
  return "idle";
}

type FilterType = "all" | "starred";

function getDateBucket(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const dateStart = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const diffDays = Math.floor((todayStart.getTime() - dateStart.getTime()) / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return "Today";
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 7) return "This Week";
    if (diffDays < 30) return "This Month";
    return date.toLocaleDateString(undefined, {
      month: "long",
      year: date.getFullYear() !== now.getFullYear() ? "numeric" : undefined,
    });
  } catch {
    return "";
  }
}

function formatTime(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const dateStart = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const diffDays = Math.floor((todayStart.getTime() - dateStart.getTime()) / (1000 * 60 * 60 * 24));

    if (diffDays < 2) {
      return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
    }
    if (diffDays < 7) {
      return date.toLocaleDateString(undefined, { weekday: "short" }) +
        " " + date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
    }
    return date.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    }) + " " + date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  } catch {
    return "";
  }
}

function formatDate(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return "Today";
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 7) return `${diffDays} days ago`;
    return date.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: date.getFullYear() !== now.getFullYear() ? "numeric" : undefined,
    });
  } catch {
    return "";
  }
}

function DateRangePicker({
  dateRange,
  onDateRangeChange,
}: {
  dateRange: DateRange | undefined;
  onDateRangeChange: (range: DateRange | undefined) => void;
}) {
  const [open, setOpen] = useState(false);

  const label = dateRange?.from
    ? dateRange.to
      ? `${format(dateRange.from, "MMM d")} - ${format(dateRange.to, "MMM d")}`
      : format(dateRange.from, "MMM d")
    : "Date range";

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant={dateRange ? "secondary" : "ghost"}
          size="xs"
          className={cn(
            "gap-1.5 text-xs font-normal",
            dateRange && "pr-1.5"
          )}
        >
          <CalendarIcon className="size-3" />
          {label}
          {dateRange && (
            <span
              role="button"
              className="ml-0.5 flex size-4 items-center justify-center rounded-sm hover:bg-muted-foreground/20"
              onClick={(e) => {
                e.stopPropagation();
                onDateRangeChange(undefined);
              }}
            >
              <X className="size-2.5" />
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="range"
          selected={dateRange}
          onSelect={(range) => {
            onDateRangeChange(range);
            if (range?.from && range?.to) {
              setOpen(false);
            }
          }}
          numberOfMonths={2}
          disabled={{ after: new Date() }}
        />
      </PopoverContent>
    </Popover>
  );
}

function FilterBar({
  filter,
  onFilterChange,
  dateRange,
  onDateRangeChange,
  categories,
  selectedCategory,
  onCategoryChange,
}: {
  filter: FilterType;
  onFilterChange: (f: FilterType) => void;
  dateRange: DateRange | undefined;
  onDateRangeChange: (range: DateRange | undefined) => void;
  categories: string[];
  selectedCategory: string | null;
  onCategoryChange: (cat: string | null) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 px-3 pb-2">
      <Button
        variant={filter === "starred" ? "secondary" : "ghost"}
        size="xs"
        className="gap-1 text-xs font-normal"
        onClick={() => onFilterChange(filter === "starred" ? "all" : "starred")}
      >
        <StarIcon className={cn("size-3", filter === "starred" && "fill-current")} />
        Starred
      </Button>

      <DateRangePicker dateRange={dateRange} onDateRangeChange={onDateRangeChange} />

      {categories.length > 0 && (
        <Popover>
          <PopoverTrigger asChild>
            <Button
              variant={selectedCategory ? "secondary" : "ghost"}
              size="xs"
              className={cn(
                "gap-1.5 text-xs font-normal",
                selectedCategory && "pr-1.5"
              )}
            >
              {selectedCategory || "Category"}
              {selectedCategory && (
                <span
                  role="button"
                  className="ml-0.5 flex size-4 items-center justify-center rounded-sm hover:bg-muted-foreground/20"
                  onClick={(e) => {
                    e.stopPropagation();
                    onCategoryChange(null);
                  }}
                >
                  <X className="size-2.5" />
                </span>
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-40 p-1" align="start">
            <div className="flex flex-col">
              {categories.map((cat) => (
                <Button
                  key={cat}
                  variant="ghost"
                  size="sm"
                  className={cn(
                    "h-7 justify-start px-2 text-xs font-normal",
                    selectedCategory === cat && "bg-accent font-medium",
                  )}
                  onClick={() => onCategoryChange(selectedCategory === cat ? null : cat)}
                >
                  {cat}
                </Button>
              ))}
            </div>
          </PopoverContent>
        </Popover>
      )}
    </div>
  );
}

function ConversationCard({
  conversation,
  isSelected,
  onSelect,
}: {
  conversation: Conversation;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const title = conversation.structured?.title || "Untitled Meeting";
  const overview = conversation.structured?.overview || "";

  return (
    <Button
      variant="ghost"
      className={cn(
        "flex h-auto w-full flex-col items-stretch gap-1 rounded-lg border border-transparent px-3 py-2.5 text-left font-normal hover:bg-secondary/50",
        isSelected && "border-border/50 bg-secondary hover:bg-secondary",
      )}
      onClick={onSelect}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">
          {title}
        </span>
        <span className="shrink-0 text-xs text-muted-foreground">
          {formatTime(conversation.created_at)}
        </span>
      </div>
      {overview && (
        <p className="truncate text-xs leading-relaxed text-muted-foreground">
          {overview}
        </p>
      )}
      {conversation.starred && (
        <span className="flex items-center gap-1 text-xs font-medium text-primary">
          <Star className="size-3 fill-current" />
          Starred
        </span>
      )}
    </Button>
  );
}

const SPEAKER_COLORS = [
  "text-blue-400",
  "text-emerald-400",
  "text-amber-400",
  "text-purple-400",
  "text-rose-400",
  "text-cyan-400",
  "text-orange-400",
  "text-teal-400",
];

function getSpeakerColor(speaker: string, speakers: string[]): string {
  const idx = speakers.indexOf(speaker);
  return SPEAKER_COLORS[idx % SPEAKER_COLORS.length];
}

function formatSpeakerName(speaker: string): string {
  return speaker
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function TranscriptView({ segments }: { segments: TranscriptSegment[] }) {
  const speakers = useMemo(() => {
    const seen: string[] = [];
    for (const seg of segments) {
      if (!seen.includes(seg.speaker)) seen.push(seg.speaker);
    }
    return seen;
  }, [segments]);

  const grouped = useMemo(() => {
    const groups: { speaker: string; isUser: boolean; texts: string[]; start: number }[] = [];
    for (const seg of segments) {
      const isUser = seg.speaker === "SPEAKER_0";
      const last = groups[groups.length - 1];
      if (last && last.speaker === seg.speaker) {
        last.texts.push(seg.text);
      } else {
        groups.push({ speaker: seg.speaker, isUser, texts: [seg.text], start: seg.start });
      }
    }
    return groups;
  }, [segments]);

  return (
    <div className="flex flex-col gap-4">
      {grouped.map((group, i) => (
        <Message key={i} from={group.isUser ? "user" : "assistant"}>
          <div
            className={cn(
              "flex items-center gap-2",
              group.isUser ? "self-end" : "self-start",
            )}
          >
            <span
              className={cn(
                "text-xs font-semibold",
                getSpeakerColor(group.speaker, speakers),
              )}
            >
              {formatSpeakerLabel(group.speaker, group.isUser)}
            </span>
            <span className="text-[10px] text-muted-foreground/60">
              {formatDuration(group.start)}
            </span>
          </div>
          <MessageContent className="leading-relaxed">
            {group.texts.join(" ")}
          </MessageContent>
        </Message>
      ))}
    </div>
  );
}

function ConversationDetail({
  conversation,
  transcriptOpen,
  onToggleTranscript,
}: {
  conversation: Conversation;
  transcriptOpen: boolean;
  onToggleTranscript: () => void;
}) {
  const title = conversation.structured?.title || "Untitled Meeting";
  const overview = conversation.structured?.overview || "";
  const segments = conversation.transcript_segments;
  const duration = segments && segments.length > 0
    ? segments[segments.length - 1].end - segments[0].start
    : 0;

  const apps = useAppStore((s) => s.apps);
  const loadApps = useAppStore((s) => s.loadApps);
  useEffect(() => {
    if (apps.length === 0) loadApps();
  }, [apps.length, loadApps]);

  const hasResults = (conversation.apps_results?.length ?? 0) > 0;
  const hasSegments = !!segments && segments.length > 0;

  return (
    <div className="flex flex-col">
      {/* Header */}
      <div className="flex flex-col gap-3 border-b border-border/50 px-6 py-5">
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-base font-semibold text-foreground">{title}</h3>
          {hasResults && hasSegments && (
            <Button
              variant={transcriptOpen ? "secondary" : "ghost"}
              size="xs"
              onClick={onToggleTranscript}
            >
              <FileText className="size-3" />
              Transcript
            </Button>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span>{formatDate(conversation.created_at)}</span>
          {duration > 0 && (
            <>
              <span className="text-border">|</span>
              <span className="flex items-center gap-1">
                <Clock className="size-3" />
                {formatDuration(duration)}
              </span>
            </>
          )}
          {hasSegments && (
            <>
              <span className="text-border">|</span>
              <span className="flex items-center gap-1">
                <User className="size-3" />
                {[...new Set(segments!.map((s) => s.speaker))].length} speakers
              </span>
            </>
          )}
        </div>
        {overview && !hasResults && (
          <p className="text-sm leading-relaxed text-muted-foreground">{overview}</p>
        )}
      </div>

      {hasResults ? (
        <AppResultsFull conversation={conversation} />
      ) : (
        <>
          <AppInsightsEmpty conversation={conversation} />
          {hasSegments && (
            <div className="flex-1 overflow-y-auto px-3 py-3">
              <TranscriptView segments={segments!} />
            </div>
          )}
        </>
      )}
    </div>
  );
}

function DetailPanel({ conversation }: { conversation: Conversation }) {
  const [transcriptOpen, setTranscriptOpen] = useState(false);

  // Reset the sidebar state when switching conversations.
  useEffect(() => {
    setTranscriptOpen(false);
  }, [conversation.id]);

  const segments = conversation.transcript_segments;
  const hasResults = (conversation.apps_results?.length ?? 0) > 0;
  const hasSegments = !!segments && segments.length > 0;
  const canToggleSidebar = hasResults && hasSegments;

  return (
    <>
      <div className="flex-1 overflow-y-auto">
        <ConversationDetail
          conversation={conversation}
          transcriptOpen={transcriptOpen}
          onToggleTranscript={() => setTranscriptOpen((v) => !v)}
        />
      </div>
      <AnimatePresence initial={false}>
        {canToggleSidebar && transcriptOpen && (
          <TranscriptSidebar
            onClose={() => setTranscriptOpen(false)}
            segments={segments!}
          />
        )}
      </AnimatePresence>
    </>
  );
}

const SIDEBAR_WIDTH = 360;

function TranscriptSidebar({
  onClose,
  segments,
}: {
  onClose: () => void;
  segments: TranscriptSegment[];
}) {
  return (
    <motion.aside
      className="flex shrink-0 flex-col overflow-hidden border-l border-border/50 bg-background"
      initial={{ width: 0, opacity: 0 }}
      animate={{ width: SIDEBAR_WIDTH, opacity: 1 }}
      exit={{ width: 0, opacity: 0 }}
      transition={{ duration: 0.24, ease: [0.4, 0, 0.2, 1] }}
    >
      <div
        className="flex h-full flex-col"
        style={{ width: SIDEBAR_WIDTH }}
      >
        <div className="flex items-center justify-between border-b border-border/50 px-4 py-3">
          <h4 className="text-sm font-semibold text-foreground">Transcript</h4>
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={onClose}
            aria-label="Close transcript"
          >
            <X className="size-3.5" />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto px-3 py-3">
          <TranscriptView segments={segments} />
        </div>
      </div>
    </motion.aside>
  );
}

// ---------------------------------------------------------------------------
// Live (in-progress) meeting
// ---------------------------------------------------------------------------

function LiveMeetingCard({
  isSelected,
  onSelect,
}: {
  isSelected: boolean;
  onSelect: () => void;
}) {
  const isRecording = useAudioStore((s) => s.isRecording);
  const isProcessing = useAudioStore((s) => s.isProcessing);
  const recordingStartedAt = useAudioStore((s) => s.recordingStartedAt);
  const liveSegments = useAudioStore((s) => s.liveSegments);
  const livePartial = useAudioStore((s) => s.livePartialBySpeaker);
  const [, forceTick] = useState(0);

  useEffect(() => {
    if (!isRecording) return;
    const id = setInterval(() => forceTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [isRecording]);

  if (!isRecording && !isProcessing) return null;

  const elapsedSec = recordingStartedAt
    ? Math.floor((Date.now() - recordingStartedAt) / 1000)
    : 0;
  const minutes = Math.floor(elapsedSec / 60);
  const seconds = elapsedSec % 60;
  const elapsed = `${minutes}:${seconds.toString().padStart(2, "0")}`;

  const partialPreview = Object.values(livePartial).join(" ").trim();
  const lastFinal = liveSegments[liveSegments.length - 1]?.text ?? "";
  const preview = partialPreview || lastFinal || "Waiting for speech…";

  return (
    <Button
      variant="ghost"
      className={cn(
        "flex h-auto w-full flex-col items-stretch gap-1.5 rounded-lg border px-3 py-2.5 text-left font-normal",
        isSelected
          ? isRecording
            ? "border-red-500/40 bg-red-500/10 hover:bg-red-500/10"
            : "border-blue-500/40 bg-blue-500/10 hover:bg-blue-500/10"
          : isRecording
            ? "border-red-500/20 bg-red-500/5 hover:bg-red-500/10"
            : "border-blue-500/20 bg-blue-500/5 hover:bg-blue-500/10",
      )}
      onClick={onSelect}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          {isRecording ? (
            <span className="relative flex size-2 shrink-0">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-red-500/60" />
              <span className="relative inline-flex size-2 rounded-full bg-red-500" />
            </span>
          ) : (
            <Loader2 className="size-3 shrink-0 animate-spin text-blue-400" />
          )}
          <span className="truncate text-sm font-medium text-foreground">
            {isRecording ? "Live meeting" : "Saving meeting…"}
          </span>
        </div>
        {isRecording && (
          <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
            {elapsed}
          </span>
        )}
      </div>
      <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">
        {isProcessing ? "Writing summary and action items…" : preview}
      </p>
    </Button>
  );
}

function formatSpeakerLabel(speaker: string, isUser: boolean): string {
  if (isUser) return "You";
  return formatSpeakerName(speaker);
}

function SpeakersSidebar({
  segments,
  partialBySpeaker,
}: {
  segments: LiveSegment[];
  partialBySpeaker: Record<string, string>;
}) {
  const stats = useMemo(() => {
    const map = new Map<
      string,
      { speaker: string; isUser: boolean; count: number; lastText: string }
    >();
    for (const s of segments) {
      const prev = map.get(s.speaker);
      if (prev) {
        prev.count += 1;
        prev.lastText = s.text;
      } else {
        map.set(s.speaker, {
          speaker: s.speaker,
          isUser: s.isUser,
          count: 1,
          lastText: s.text,
        });
      }
    }
    // Include any speaker currently mid-utterance (interim only, no finals yet)
    for (const speaker of Object.keys(partialBySpeaker)) {
      if (!map.has(speaker)) {
        map.set(speaker, {
          speaker,
          isUser: false,
          count: 0,
          lastText: partialBySpeaker[speaker],
        });
      }
    }
    return Array.from(map.values());
  }, [segments, partialBySpeaker]);

  const speakers = useMemo(() => stats.map((s) => s.speaker), [stats]);

  return (
    <div className="flex flex-col gap-2 px-3 py-4">
      <div className="flex items-center gap-1.5 px-1 pb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground/70">
        <User className="size-3" />
        Speakers
        {stats.length > 0 && (
          <span className="ml-auto tabular-nums">{stats.length}</span>
        )}
      </div>
      {stats.length === 0 ? (
        <p className="px-1 text-xs text-muted-foreground/60">
          Will appear as they talk.
        </p>
      ) : (
        <div className="flex flex-col">
          {stats.map((s) => {
            const isActive = Boolean(partialBySpeaker[s.speaker]);
            return (
              <div
                key={s.speaker}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-2 py-1.5 transition-colors",
                  isActive ? "bg-red-500/5" : "hover:bg-secondary/40",
                )}
              >
                <div
                  className={cn(
                    "flex size-6 shrink-0 items-center justify-center rounded-full bg-secondary text-[11px] font-medium",
                    getSpeakerColor(s.speaker, speakers),
                  )}
                >
                  {formatSpeakerLabel(s.speaker, s.isUser).charAt(0)}
                </div>
                <div className="flex min-w-0 flex-1 flex-col leading-tight">
                  <span
                    className={cn(
                      "truncate text-xs font-medium",
                      isActive ? "text-foreground" : "text-foreground/80",
                    )}
                  >
                    {formatSpeakerLabel(s.speaker, s.isUser)}
                  </span>
                  <span className="text-[10px] text-muted-foreground">
                    {s.count === 0
                      ? "speaking"
                      : `${s.count} turn${s.count === 1 ? "" : "s"}`}
                  </span>
                </div>
                {isActive && (
                  <span className="relative flex size-1.5 shrink-0">
                    <span className="absolute inline-flex size-full animate-ping rounded-full bg-red-500/60" />
                    <span className="relative inline-flex size-1.5 rounded-full bg-red-500" />
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function LiveTranscriptView({
  segments,
  partialBySpeaker,
}: {
  segments: LiveSegment[];
  partialBySpeaker: Record<string, string>;
}) {
  const speakers = useMemo(() => {
    const seen: string[] = [];
    for (const seg of segments) {
      if (!seen.includes(seg.speaker)) seen.push(seg.speaker);
    }
    for (const sp of Object.keys(partialBySpeaker)) {
      if (!seen.includes(sp)) seen.push(sp);
    }
    return seen;
  }, [segments, partialBySpeaker]);

  const grouped = useMemo(() => {
    const groups: {
      speaker: string;
      isUser: boolean;
      texts: string[];
      start: number;
    }[] = [];
    for (const seg of segments) {
      const last = groups[groups.length - 1];
      if (last && last.speaker === seg.speaker) {
        last.texts.push(seg.text);
      } else {
        groups.push({
          speaker: seg.speaker,
          isUser: seg.isUser,
          texts: [seg.text],
          start: seg.start,
        });
      }
    }
    return groups;
  }, [segments]);

  const partials = Object.entries(partialBySpeaker).filter(([, text]) => text);

  if (grouped.length === 0 && partials.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 px-8 text-center">
        <span className="relative flex size-3">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-red-500/60" />
          <span className="relative inline-flex size-3 rounded-full bg-red-500" />
        </span>
        <p className="max-w-sm text-sm text-muted-foreground">
          Listening… speak and your words will appear here in real time.
        </p>
      </div>
    );
  }

  return (
    <LiveConversation className="min-h-0">
      <LiveConversationContent className="gap-4 px-4 py-4 pb-20">
        {grouped.map((group, i) => (
          <Message key={i} from={group.isUser ? "user" : "assistant"}>
            <span
              className={cn(
                "text-xs font-semibold",
                group.isUser ? "self-end" : "self-start",
                getSpeakerColor(group.speaker, speakers),
              )}
            >
              {formatSpeakerLabel(group.speaker, group.isUser)}
            </span>
            <MessageContent className="leading-relaxed">
              {group.texts.join(" ")}
            </MessageContent>
          </Message>
        ))}
        {partials.map(([speaker, text]) => {
          const isUser = segments.find((s) => s.speaker === speaker)?.isUser ?? false;
          return (
            <Message key={`partial-${speaker}`} from={isUser ? "user" : "assistant"} className="opacity-70">
              <span
                className={cn(
                  "text-xs font-semibold",
                  isUser ? "self-end" : "self-start",
                  getSpeakerColor(speaker, speakers),
                )}
              >
                {formatSpeakerLabel(speaker, isUser)}
              </span>
              <MessageContent className="italic leading-relaxed">
                {text}
              </MessageContent>
            </Message>
          );
        })}
      </LiveConversationContent>
      <LiveConversationScrollButton />
    </LiveConversation>
  );
}

function LiveMeetingDetail() {
  const isRecording = useAudioStore((s) => s.isRecording);
  const isProcessing = useAudioStore((s) => s.isProcessing);
  const recordingStartedAt = useAudioStore((s) => s.recordingStartedAt);
  const liveSegments = useAudioStore((s) => s.liveSegments);
  const livePartial = useAudioStore((s) => s.livePartialBySpeaker);
  const stopAudio = useAudioStore((s) => s.stopAudio);
  const language = useAudioStore((s) => s.language);
  const setLanguage = useAudioStore((s) => s.setLanguage);
  const [, forceTick] = useState(0);

  useEffect(() => {
    if (!isRecording) return;
    const id = setInterval(() => forceTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [isRecording]);

  const elapsedSec = recordingStartedAt
    ? Math.floor((Date.now() - recordingStartedAt) / 1000)
    : 0;
  const minutes = Math.floor(elapsedSec / 60);
  const seconds = elapsedSec % 60;
  const elapsed = `${minutes}:${seconds.toString().padStart(2, "0")}`;

  return (
    <div className="flex h-full min-h-0">
      {/* Main content */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="flex shrink-0 items-center gap-3 border-b border-border/50 px-5 py-3">
          <div className="flex min-w-0 flex-1 items-center gap-2.5">
            {isRecording ? (
              <span className="relative flex size-2 shrink-0">
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-red-500/60" />
                <span className="relative inline-flex size-2 rounded-full bg-red-500" />
              </span>
            ) : (
              <Loader2 className="size-3 shrink-0 animate-spin text-blue-400" />
            )}
            <h3 className="truncate whitespace-nowrap text-sm font-semibold text-foreground">
              {isRecording ? "Live meeting" : "Saving meeting"}
            </h3>
            <span className="shrink-0 whitespace-nowrap text-xs tabular-nums text-muted-foreground">
              {isRecording ? elapsed : "15–30s…"}
            </span>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Tabs
              value={language}
              onValueChange={(v) => void setLanguage(v as typeof language)}
              aria-label="Transcription language"
            >
              <TabsList className="h-7">
                {TRANSCRIPTION_LANGUAGES.map((l) => (
                  <TabsTrigger
                    key={l.code}
                    value={l.code}
                    title={l.label}
                    className="px-2 text-[11px] font-medium uppercase tracking-wide"
                  >
                    {l.code === "pt-BR" ? "PT" : "EN"}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
            {isRecording && (
              <Button
                variant="destructive"
                size="sm"
                className="h-7 gap-1.5 px-2.5 text-xs"
                onClick={() => void stopAudio()}
              >
                <Square className="size-3 fill-current" />
                Stop
              </Button>
            )}
          </div>
        </div>
        {isProcessing && liveSegments.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 px-8 text-center">
            <Loader2 className="size-6 animate-spin text-blue-400" />
            <p className="max-w-sm text-sm text-muted-foreground">
              Writing summary, title and action items.
            </p>
          </div>
        ) : (
          <LiveTranscriptView
            segments={liveSegments}
            partialBySpeaker={livePartial}
          />
        )}
      </div>
      {/* Speakers sidebar */}
      <div className="flex w-[240px] shrink-0 flex-col overflow-y-auto border-l border-border/50">
        <SpeakersSidebar
          segments={liveSegments}
          partialBySpeaker={livePartial}
        />
      </div>
    </div>
  );
}

function ConversationsEmptyState() {
  const audioEnabled = useAudioStore((s) => s.audioEnabled);
  const isRecording = useAudioStore((s) => s.isRecording);
  const inCommercialHours = useAudioStore((s) => s.inCommercialHours);
  const liveTranscript = useAudioStore((s) => s.liveTranscript);
  const isProcessing = useAudioStore((s) => s.isProcessing);
  const toggleAudio = useAudioStore((s) => s.toggleAudio);
  const stopAudio = useAudioStore((s) => s.stopAudio);
  const personaState = audioStateToPersona({ audioEnabled, isRecording, inCommercialHours, isProcessing });

  const heading = isProcessing
    ? "Processing meeting…"
    : isRecording
      ? "Listening"
      : !audioEnabled
        ? "Audio is off"
        : !inCommercialHours
          ? "Outside recording hours"
          : "Ready to listen";

  const subline = isProcessing
    ? "Generating title, summary, and action items. This takes 15–30 seconds."
    : isRecording
      ? "Speak — I'll transcribe and save this meeting when you stop."
      : !audioEnabled
        ? "Turn the microphone on and I'll capture your next meeting."
        : !inCommercialHours
          ? "Recording is scheduled for Mon–Fri, 9am–5pm."
          : "Start a meeting, or pick one from the list.";

  return (
    <div className="flex h-full flex-col items-center justify-center gap-6 px-8 text-center">
      <PersonaSlot state={personaState} />
      <div className="flex flex-col items-center gap-1.5">
        <h3 className="text-base font-medium text-foreground">{heading}</h3>
        <p className="max-w-sm text-sm text-muted-foreground">{subline}</p>
      </div>
      {isRecording && liveTranscript && (
        <div className="max-w-md rounded-lg border border-border/50 bg-secondary/40 px-4 py-2.5">
          <p className="line-clamp-3 text-sm italic text-foreground/80">
            {liveTranscript}
          </p>
        </div>
      )}
      {!isProcessing && (
        <div className="flex flex-col items-center gap-2">
          {isRecording ? (
            <Button
              variant="destructive"
              size="sm"
              className="gap-2"
              onClick={() => void stopAudio()}
            >
              <Square className="size-3.5 fill-current" />
              Stop and save meeting
            </Button>
          ) : inCommercialHours ? (
            <Button
              variant={audioEnabled ? "secondary" : "default"}
              size="sm"
              className="gap-2"
              onClick={() => void toggleAudio()}
            >
              {audioEnabled ? (
                <>
                  <MicOff className="size-3.5" />
                  Turn microphone off
                </>
              ) : (
                <>
                  <Mic className="size-3.5" />
                  Start a meeting
                </>
              )}
            </Button>
          ) : null}
        </div>
      )}
    </div>
  );
}

function PersonaSlot({ state }: { state: PersonaState }) {
  const isListening = state === "listening";
  const isAsleep = state === "asleep";
  const isThinking = state === "thinking";

  return (
    <div className="relative flex size-32 items-center justify-center">
      {/* Outer aura — only when active */}
      {!isAsleep && (
        <div
          className={cn(
            "absolute inset-0 rounded-full blur-2xl transition-opacity duration-700",
            isListening
              ? "animate-orb-pulse bg-red-500/30 opacity-100"
              : isThinking
                ? "animate-orb-pulse bg-blue-500/25 opacity-100"
                : "bg-foreground/10 opacity-60",
          )}
        />
      )}

      {/* Core orb */}
      <div
        className={cn(
          "relative size-24 rounded-full transition-all duration-700",
          "bg-[radial-gradient(circle_at_30%_30%,_var(--tw-gradient-from),_var(--tw-gradient-to))]",
          isAsleep
            ? "from-muted to-muted-foreground/30 opacity-50"
            : isListening
              ? "animate-orb-breathe from-red-300 to-red-700 shadow-[0_0_40px_rgba(239,68,68,0.5)]"
              : isThinking
                ? "animate-orb-breathe from-blue-300 to-blue-700 shadow-[0_0_40px_rgba(59,130,246,0.5)]"
                : "animate-orb-drift from-foreground/40 to-foreground shadow-[0_0_30px_rgba(255,255,255,0.15)]",
        )}
      >
        {/* Inner highlight */}
        <div className="absolute inset-2 rounded-full bg-gradient-to-br from-white/20 to-transparent" />
      </div>
    </div>
  );
}

export function ConversationsPage() {
  const {
    conversations,
    isLoading,
    selectedConversation,
    searchQuery,
    loadConversations,
    searchConversations,
    selectConversation,
  } = useConversationStore();

  const [filter, setFilter] = useState<FilterType>("all");
  const [dateRange, setDateRange] = useState<DateRange | undefined>();
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedLive, setSelectedLive] = useState(false);

  const isRecording = useAudioStore((s) => s.isRecording);
  const isProcessing = useAudioStore((s) => s.isProcessing);
  const processingError = useAudioStore((s) => s.processingError);
  const dismissProcessingError = useAudioStore((s) => s.dismissProcessingError);
  const liveActive = isRecording || isProcessing;

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  // Auto-focus the live meeting the moment recording starts, so the user sees
  // the transcript without clicking. Clear the selection when the live session
  // ends so a saved conversation can take focus.
  useEffect(() => {
    if (isRecording) {
      setSelectedLive(true);
      selectConversation(null);
    }
  }, [isRecording, selectConversation]);

  useEffect(() => {
    if (!liveActive) {
      setSelectedLive(false);
    }
  }, [liveActive]);

  const categories = useMemo(() => {
    const cats = new Set<string>();
    for (const c of conversations) {
      if (c.structured?.category) cats.add(c.structured.category);
    }
    return [...cats].sort();
  }, [conversations]);

  const filteredConversations = useMemo(() => {
    let result = conversations;

    // Text search
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (c) =>
          c.structured?.title?.toLowerCase().includes(q) ||
          c.structured?.overview?.toLowerCase().includes(q),
      );
    }

    // Starred filter
    if (filter === "starred") {
      result = result.filter((c) => c.starred);
    }

    // Category filter
    if (selectedCategory) {
      result = result.filter((c) => c.structured?.category === selectedCategory);
    }

    // Date range filter
    if (dateRange?.from) {
      const from = startOfDay(dateRange.from);
      const to = dateRange.to ? endOfDay(dateRange.to) : endOfDay(dateRange.from);
      result = result.filter((c) => {
        try {
          const d = new Date(c.created_at);
          return isWithinInterval(d, { start: from, end: to });
        } catch {
          return false;
        }
      });
    }

    return result;
  }, [conversations, searchQuery, filter, selectedCategory, dateRange]);

  const hasActiveFilters = filter !== "all" || !!dateRange || !!selectedCategory;

  const groupedConversations = useMemo(() => {
    const groups: { label: string; conversations: Conversation[] }[] = [];
    for (const conv of filteredConversations) {
      const bucket = getDateBucket(conv.created_at);
      const last = groups[groups.length - 1];
      if (last && last.label === bucket) {
        last.conversations.push(conv);
      } else {
        groups.push({ label: bucket, conversations: [conv] });
      }
    }
    return groups;
  }, [filteredConversations]);

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 px-6 pb-2 pt-5">
        <h2 className="text-lg font-semibold text-foreground">Meetings</h2>
      </div>
      <div className="flex flex-1 overflow-hidden">
        {/* List panel */}
        <div className="flex w-[340px] shrink-0 flex-col border-r border-border/50">
          {liveActive && (
            <div className="shrink-0 px-2 pb-2 pt-1">
              <LiveMeetingCard
                isSelected={selectedLive}
                onSelect={() => {
                  setSelectedLive(true);
                  selectConversation(null);
                }}
              />
            </div>
          )}
          {processingError && (
            <div className="shrink-0 px-2 pb-2 pt-1">
              <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2.5 text-xs text-red-400">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-red-300">Meeting not saved</p>
                  <p className="mt-0.5 leading-relaxed text-red-400/80">{processingError}</p>
                </div>
                <Button
                  variant="ghost"
                  size="icon-xs"
                  onClick={dismissProcessingError}
                  aria-label="Dismiss"
                  className="shrink-0 text-red-400/60 hover:bg-red-500/20 hover:text-red-300"
                >
                  <X className="size-3.5" />
                </Button>
              </div>
            </div>
          )}
          <div className="shrink-0 px-3 pb-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="text"
                placeholder="Search..."
                value={searchQuery}
                onChange={(e) => searchConversations(e.target.value)}
                className="h-9 bg-secondary/50 pl-9"
              />
            </div>
          </div>

          <FilterBar
            filter={filter}
            onFilterChange={setFilter}
            dateRange={dateRange}
            onDateRangeChange={setDateRange}
            categories={categories}
            selectedCategory={selectedCategory}
            onCategoryChange={setSelectedCategory}
          />

          <div className="flex-1 overflow-y-auto px-2 pb-2">
            {isLoading && conversations.length === 0 && (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                Loading...
              </div>
            )}
            {!isLoading && filteredConversations.length === 0 && (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
                <span>{searchQuery || hasActiveFilters ? "No matches" : "No meetings yet"}</span>
                {hasActiveFilters && (
                  <Button
                    variant="ghost"
                    size="xs"
                    className="text-xs"
                    onClick={() => {
                      setFilter("all");
                      setDateRange(undefined);
                      setSelectedCategory(null);
                    }}
                  >
                    Clear filters
                  </Button>
                )}
              </div>
            )}
            {groupedConversations.map((group) => (
              <div key={group.label}>
                <div className="sticky top-0 z-10 bg-background/80 px-3 pb-1 pt-3 backdrop-blur-sm">
                  <span className="text-xs font-medium text-muted-foreground">
                    {group.label}
                  </span>
                </div>
                {group.conversations.map((conv) => (
                  <ConversationCard
                    key={conv.id}
                    conversation={conv}
                    isSelected={!selectedLive && selectedConversation?.id === conv.id}
                    onSelect={() => {
                      setSelectedLive(false);
                      selectConversation(conv);
                    }}
                  />
                ))}
              </div>
            ))}
          </div>
        </div>
        {/* Detail panel */}
        <div className="flex flex-1 overflow-hidden">
          {selectedLive && liveActive ? (
            <div className="flex flex-1 flex-col overflow-hidden">
              <LiveMeetingDetail />
            </div>
          ) : selectedConversation ? (
            <DetailPanel conversation={selectedConversation} />
          ) : (
            <div className="flex-1 overflow-y-auto">
              <ConversationsEmptyState />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
