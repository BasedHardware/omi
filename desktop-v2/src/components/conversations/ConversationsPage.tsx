import { useEffect, useMemo, useState } from "react";
import { useConversationStore } from "../../stores/conversationStore";
import type { Conversation, TranscriptSegment } from "../../stores/conversationStore";
import { MessageSquareText, Star, Search, Clock, User, CalendarIcon, X, StarIcon } from "lucide-react";
import { format, isWithinInterval, startOfDay, endOfDay } from "date-fns";
import type { DateRange } from "react-day-picker";
import { Button } from "../ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { Calendar } from "../ui/calendar";
import { cn } from "@/lib/utils";

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
                <button
                  key={cat}
                  className={cn(
                    "rounded-sm px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent",
                    selectedCategory === cat && "bg-accent font-medium"
                  )}
                  onClick={() => onCategoryChange(selectedCategory === cat ? null : cat)}
                >
                  {cat}
                </button>
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
  const title = conversation.structured?.title || "Untitled Conversation";
  const overview = conversation.structured?.overview || "";

  return (
    <button
      className={`flex w-full flex-col gap-1 rounded-lg border border-transparent px-3 py-2.5 text-left font-inherit transition-colors ${
        isSelected
          ? "border-border/50 bg-secondary"
          : "hover:bg-secondary/50"
      }`}
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
    </button>
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
    const groups: { speaker: string; texts: string[]; start: number }[] = [];
    for (const seg of segments) {
      const last = groups[groups.length - 1];
      if (last && last.speaker === seg.speaker) {
        last.texts.push(seg.text);
      } else {
        groups.push({ speaker: seg.speaker, texts: [seg.text], start: seg.start });
      }
    }
    return groups;
  }, [segments]);

  return (
    <div className="flex flex-col gap-0.5">
      {grouped.map((group, i) => (
        <div key={i} className="group/seg flex gap-3 rounded-lg px-3 py-2 hover:bg-secondary/40">
          <div className="flex w-6 shrink-0 items-start justify-center pt-0.5">
            <div className={`flex size-6 items-center justify-center rounded-full bg-secondary text-xs font-medium ${getSpeakerColor(group.speaker, speakers)}`}>
              {formatSpeakerName(group.speaker).charAt(0)}
            </div>
          </div>
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <div className="flex items-center gap-2">
              <span className={`text-xs font-semibold ${getSpeakerColor(group.speaker, speakers)}`}>
                {formatSpeakerName(group.speaker)}
              </span>
              <span className="text-[10px] text-muted-foreground/60">
                {formatDuration(group.start)}
              </span>
            </div>
            <p className="text-sm leading-relaxed text-foreground/80">
              {group.texts.join(" ")}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

function ConversationDetail({ conversation }: { conversation: Conversation }) {
  const title = conversation.structured?.title || "Untitled Conversation";
  const overview = conversation.structured?.overview || "";
  const segments = conversation.transcript_segments;
  const duration = segments && segments.length > 0
    ? segments[segments.length - 1].end - segments[0].start
    : 0;

  return (
    <div className="flex flex-col">
      {/* Header */}
      <div className="flex flex-col gap-3 border-b border-border/50 px-6 py-5">
        <h3 className="text-base font-semibold text-foreground">{title}</h3>
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
          {segments && segments.length > 0 && (
            <>
              <span className="text-border">|</span>
              <span className="flex items-center gap-1">
                <User className="size-3" />
                {[...new Set(segments.map((s) => s.speaker))].length} speakers
              </span>
            </>
          )}
        </div>
        {overview && (
          <p className="text-sm leading-relaxed text-muted-foreground">{overview}</p>
        )}
      </div>

      {/* Transcript */}
      {segments && segments.length > 0 && (
        <div className="flex-1 overflow-y-auto px-3 py-3">
          <TranscriptView segments={segments} />
        </div>
      )}
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

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

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
        <h2 className="text-lg font-semibold text-foreground">Conversations</h2>
      </div>
      <div className="flex flex-1 overflow-hidden">
        {/* List panel */}
        <div className="flex w-[340px] shrink-0 flex-col border-r border-border/50">
          <div className="shrink-0 px-3 pb-2">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                className="w-full rounded-lg border border-border/50 bg-secondary/50 py-2 pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-border focus:outline-none"
                placeholder="Search..."
                value={searchQuery}
                onChange={(e) => searchConversations(e.target.value)}
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
                <span>{searchQuery || hasActiveFilters ? "No matches" : "No conversations yet"}</span>
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
                    isSelected={selectedConversation?.id === conv.id}
                    onSelect={() => selectConversation(conv)}
                  />
                ))}
              </div>
            ))}
          </div>
        </div>
        {/* Detail panel */}
        <div className="flex flex-1 flex-col overflow-y-auto">
          {selectedConversation ? (
            <ConversationDetail conversation={selectedConversation} />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-muted-foreground">
              <MessageSquareText className="size-8 opacity-40" />
              <span className="text-sm">Select a conversation</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
