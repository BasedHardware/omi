import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRewindStore } from "../../stores/rewindStore";
import { Search, X, Circle, Square, Clock, Monitor, FileText, ChevronDown, ChevronUp, Loader2, Trash2 } from "lucide-react";

// ---------------------------------------------------------------------------
// Hash-based color for app names (matches Swift InteractiveTimelineBar)
// ---------------------------------------------------------------------------

/** Derive a muted HSL color from an app name string. */
function appNameToColor(appName: string): string {
  let hash = 0;
  for (let i = 0; i < appName.length; i++) {
    hash = (hash * 31 + appName.charCodeAt(i)) | 0;
  }
  const hue = ((hash >>> 0) % 360);
  return `hsl(${hue}, 40%, 50%)`;
}

// ---------------------------------------------------------------------------
// Debounce hook
// ---------------------------------------------------------------------------

function useDebounce<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState<T>(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RewindPage() {
  const {
    isCapturing,
    rewindEnabled,
    inCommercialHours,
    screenshots,
    selectedScreenshot,
    searchQuery,
    searchResults,
    isSearching,
    toggleRewind,
    selectScreenshot,
    search,
    clearSearch,
    loadCaptureState,
    isLoadingHistory,
    deleteScreenshot,
    clearAllScreenshots,
  } = useRewindStore();

  const [ocrExpanded, setOcrExpanded] = useState(false);
  // Controlled input value — may be ahead of the debounced search query.
  const [inputValue, setInputValue] = useState("");
  const loadedRef = useRef(false);
  // Track whether the user manually picked a frame — if so, stop auto-selecting.
  const userSelectedRef = useRef(false);

  // Debounce the search input by 300 ms before firing the FTS5 query.
  const debouncedInput = useDebounce(inputValue, 300);

  // Load capture state (DB history) on mount.
  useEffect(() => {
    if (!loadedRef.current) {
      loadedRef.current = true;
      loadCaptureState();
    }
  }, [loadCaptureState]);

  // Fire FTS5 search whenever the debounced value changes.
  useEffect(() => {
    if (debouncedInput.trim()) {
      search(debouncedInput);
    } else {
      clearSearch();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedInput]);

  // Auto-select latest screenshot only when the user hasn't picked one manually.
  useEffect(() => {
    if (screenshots.length > 0 && !searchQuery && !userSelectedRef.current) {
      const latest = screenshots[0]; // newest is first
      if (!selectedScreenshot || selectedScreenshot.id !== latest.id) {
        void selectScreenshot(latest.id);
      }
    }
  }, [screenshots, searchQuery, selectedScreenshot, selectScreenshot]);

  // Reset manual-selection flag when capture stops (so next capture auto-follows again).
  useEffect(() => {
    if (!isCapturing) {
      userSelectedRef.current = false;
    }
  }, [isCapturing]);

  const displayedScreenshots = searchQuery ? searchResults : screenshots;

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setInputValue(e.target.value);
  };

  const handleClearSearch = useCallback(() => {
    setInputValue("");
    clearSearch();
  }, [clearSearch]);

  const handleThumbnailClick = useCallback(
    (id: string) => {
      userSelectedRef.current = true;
      void selectScreenshot(id);
    },
    [selectScreenshot]
  );

  const parseTimestamp = (timestamp: string): Date => {
    // Handle raw unix millis strings (legacy DB entries).
    if (/^\d{10,}$/.test(timestamp.trim())) {
      return new Date(Number(timestamp));
    }
    return new Date(timestamp);
  };

  const formatTime = (timestamp: string) => {
    const date = parseTimestamp(timestamp);
    if (isNaN(date.getTime())) return "--:--";
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };

  const formatFullTime = (timestamp: string) => {
    const date = parseTimestamp(timestamp);
    if (isNaN(date.getTime())) return "Unknown date";
    return date.toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  };

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-6 pt-5 pb-4 shrink-0">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-semibold text-[var(--text-primary)]">
            Rewind
          </h2>
          {isCapturing && (
            <div className="flex items-center gap-1.5">
              <span className="relative flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500 opacity-75" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-red-500" />
              </span>
              <span className="text-xs font-medium text-red-400">
                Recording
              </span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {screenshots.length > 0 && (
            <button
              onClick={() => void clearAllScreenshots()}
              className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-red-400 hover:bg-red-500/10 border border-red-500/20 transition-colors"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Clear All
            </button>
          )}
          <button
            onClick={toggleRewind}
            title={
              rewindEnabled && !isCapturing && !inCommercialHours
                ? "Rewind is on but paused outside commercial hours (Mon-Fri 9am-5pm)"
                : undefined
            }
            className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              isCapturing
                ? "bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/30"
                : rewindEnabled
                  ? "bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 border border-amber-500/30"
                  : "bg-[var(--app-accent)] text-white hover:bg-[var(--app-accent-hover)]"
            }`}
          >
            {isCapturing ? (
              <>
                <Square className="h-3.5 w-3.5" />
                Stop
              </>
            ) : rewindEnabled ? (
              <>
                <Circle className="h-3.5 w-3.5" />
                Paused (off hours)
              </>
            ) : (
              <>
                <Circle className="h-3.5 w-3.5" />
                Start Capture
              </>
            )}
          </button>
        </div>
      </div>

      {/* Search bar */}
      <div className="px-6 pb-4 shrink-0">
        <div className="relative">
          {isSearching ? (
            <Loader2 className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--app-accent)] animate-spin" />
          ) : (
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-secondary)]" />
          )}
          <input
            type="text"
            value={inputValue}
            onChange={handleSearchChange}
            placeholder="Search your screen history..."
            className="w-full rounded-lg border border-[var(--app-border)] bg-[var(--bg-tertiary)] py-2.5 pl-10 pr-10 text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-secondary)] transition-colors focus:border-[var(--app-accent)]"
          />
          {inputValue && (
            <button
              onClick={handleClearSearch}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
        {/* Search result count */}
        {searchQuery && !isSearching && (
          <p className="mt-1.5 text-xs text-[var(--text-secondary)] pl-1">
            {searchResults.length === 0
              ? "No results found"
              : `${searchResults.length} result${searchResults.length === 1 ? "" : "s"}`}
          </p>
        )}
      </div>

      {/* Main content area */}
      <div className="flex-1 overflow-y-auto px-6 pb-4 min-h-0">
        {isLoadingHistory && screenshots.length === 0 ? (
          /* History loading state */
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <Loader2 className="h-8 w-8 text-[var(--text-secondary)] animate-spin" />
            <p className="text-sm text-[var(--text-secondary)]">Loading history...</p>
          </div>
        ) : selectedScreenshot ? (
          <div className="flex flex-col gap-3 h-full">
            {/* Screenshot viewer */}
            <div className="relative flex-1 min-h-0 rounded-xl overflow-hidden border border-[var(--app-border)] bg-[var(--bg-secondary)]">
              {selectedScreenshot.data ? (
                <img
                  src={`data:image/jpeg;base64,${selectedScreenshot.data}`}
                  alt={selectedScreenshot.windowTitle || "Screenshot"}
                  className="h-full w-full object-contain"
                />
              ) : (
                /* Placeholder while image data is being lazy-loaded */
                <div className="flex h-full w-full items-center justify-center">
                  <Loader2 className="h-8 w-8 text-[var(--text-secondary)] animate-spin" />
                </div>
              )}
              {/* Overlay header */}
              <div className="absolute top-0 left-0 right-0 bg-gradient-to-b from-black/70 to-transparent px-4 py-3">
                <div className="flex items-center gap-2 text-sm">
                  <Monitor className="h-4 w-4 text-white/80 shrink-0" />
                  <span className="font-medium text-white/90 truncate">
                    {selectedScreenshot.appName || "Unknown App"}
                  </span>
                  {selectedScreenshot.windowTitle && (
                    <>
                      <span className="text-white/40">-</span>
                      <span className="text-white/60 truncate">
                        {selectedScreenshot.windowTitle}
                      </span>
                    </>
                  )}
                  <div className="ml-auto flex items-center gap-3 shrink-0">
                    <div className="flex items-center gap-1.5">
                      <Clock className="h-3.5 w-3.5 text-white/60" />
                      <span className="text-xs text-white/60">
                        {formatFullTime(selectedScreenshot.timestamp)}
                      </span>
                    </div>
                    <button
                      onClick={() => deleteScreenshot(selectedScreenshot.id)}
                      className="flex items-center justify-center h-6 w-6 rounded hover:bg-white/20 transition-colors"
                      title="Delete screenshot"
                    >
                      <Trash2 className="h-3.5 w-3.5 text-white/60 hover:text-red-400" />
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* OCR text panel (collapsible) */}
            {selectedScreenshot.ocrText && (
              <div className="shrink-0 rounded-lg border border-[var(--app-border)] bg-[var(--bg-secondary)]">
                <button
                  onClick={() => setOcrExpanded(!ocrExpanded)}
                  className="flex w-full items-center justify-between px-4 py-2.5 text-sm font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <FileText className="h-4 w-4" />
                    <span>Extracted Text</span>
                    <span className="text-xs text-[var(--text-secondary)] opacity-60">
                      {selectedScreenshot.ocrText.split("\n").length} blocks
                    </span>
                  </div>
                  {ocrExpanded ? (
                    <ChevronUp className="h-4 w-4" />
                  ) : (
                    <ChevronDown className="h-4 w-4" />
                  )}
                </button>
                {ocrExpanded && (
                  <div className="border-t border-[var(--app-border)] px-4 py-3 max-h-48 overflow-y-auto">
                    <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--text-secondary)] font-mono">
                      {selectedScreenshot.ocrText}
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          /* Empty state */
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-[var(--bg-secondary)] border border-[var(--app-border)]">
              <Monitor className="h-8 w-8 text-[var(--text-secondary)]" />
            </div>
            <h3 className="text-lg font-medium text-[var(--text-primary)]">
              No screenshots yet
            </h3>
            <p className="max-w-sm text-sm text-[var(--text-secondary)]">
              Start capturing to record your screen activity. Screenshots will
              appear here with searchable text.
            </p>
          </div>
        )}
      </div>

      {/* Timeline bar — colored segments like Swift InteractiveTimelineBar */}
      {displayedScreenshots.length > 0 && (
        <TimelineBar
          screenshots={displayedScreenshots}
          selectedId={selectedScreenshot?.id ?? null}
          onSelect={handleThumbnailClick}
          formatTime={formatTime}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// TimelineBar — interactive colored-segment scrubber
// ---------------------------------------------------------------------------

interface TimelineBarProps {
  screenshots: import("../../stores/rewindStore").Screenshot[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  formatTime: (ts: string) => string;
}

function TimelineBar({ screenshots, selectedId, onSelect, formatTime }: TimelineBarProps) {
  const barRef = useRef<HTMLDivElement>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  // Screenshots are newest-first in the array; reverse for left-to-right chronological display.
  const chronological = useMemo(() => [...screenshots].reverse(), [screenshots]);

  const selectedIndex = useMemo(() => {
    if (!selectedId) return -1;
    return chronological.findIndex((s) => s.id === selectedId);
  }, [chronological, selectedId]);

  const handleBarClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const bar = barRef.current;
      if (!bar || chronological.length === 0) return;
      const rect = bar.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const fraction = Math.max(0, Math.min(1, x / rect.width));
      const idx = Math.min(
        chronological.length - 1,
        Math.floor(fraction * chronological.length)
      );
      onSelect(chronological[idx].id);
    },
    [chronological, onSelect]
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const bar = barRef.current;
      if (!bar || chronological.length === 0) return;
      const rect = bar.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const fraction = Math.max(0, Math.min(1, x / rect.width));
      const idx = Math.min(
        chronological.length - 1,
        Math.floor(fraction * chronological.length)
      );
      setHoverIndex(idx);
    },
    [chronological]
  );

  const handleMouseLeave = useCallback(() => setHoverIndex(null), []);

  // Playhead position as a percentage.
  const playheadPct =
    selectedIndex >= 0
      ? ((selectedIndex + 0.5) / chronological.length) * 100
      : null;

  // Hover position as a percentage.
  const hoverPct =
    hoverIndex !== null
      ? ((hoverIndex + 0.5) / chronological.length) * 100
      : null;

  // Time labels: oldest (left), newest (right).
  const oldestTime = chronological.length > 0 ? formatTime(chronological[0].timestamp) : "";
  const newestTime =
    chronological.length > 0
      ? formatTime(chronological[chronological.length - 1].timestamp)
      : "";

  // Hovered screenshot info for tooltip.
  const hoveredScreenshot = hoverIndex !== null ? chronological[hoverIndex] : null;

  return (
    <div className="shrink-0 border-t border-[var(--app-border)] bg-[var(--bg-secondary)] px-5 py-3">
      {/* Tooltip */}
      {hoveredScreenshot && hoverPct !== null && (
        <div
          className="relative mb-1.5 flex justify-start pointer-events-none"
          style={{ paddingLeft: `${hoverPct}%`, transform: "translateX(-50%)" }}
        >
          <div className="inline-flex items-center gap-1.5 rounded-md bg-black/80 px-2 py-1 text-[10px] text-white/80 whitespace-nowrap">
            <span className="font-medium">{hoveredScreenshot.appName || "Unknown"}</span>
            <span className="text-white/40">·</span>
            <span>{formatTime(hoveredScreenshot.timestamp)}</span>
          </div>
        </div>
      )}

      {/* Bar container */}
      <div
        ref={barRef}
        className="relative h-8 w-full cursor-pointer rounded overflow-hidden select-none"
        style={{ backgroundColor: "rgba(255,255,255,0.08)" }}
        onClick={handleBarClick}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
      >
        {/* Colored segments */}
        <div className="absolute inset-0 flex">
          {chronological.map((s, i) => (
            <div
              key={s.id}
              className="h-full transition-opacity"
              style={{
                flex: 1,
                backgroundColor: appNameToColor(s.appName || "unknown"),
                opacity: selectedIndex === i ? 1 : 0.6,
              }}
            />
          ))}
        </div>

        {/* Hover indicator */}
        {hoverPct !== null && hoverIndex !== selectedIndex && (
          <div
            className="absolute top-0 h-full w-[2px] bg-white/50 pointer-events-none"
            style={{ left: `${hoverPct}%`, transform: "translateX(-50%)" }}
          />
        )}

        {/* Playhead */}
        {playheadPct !== null && (
          <>
            {/* Glow */}
            <div
              className="absolute top-[-2px] bottom-[-2px] w-2 rounded pointer-events-none"
              style={{
                left: `${playheadPct}%`,
                transform: "translateX(-50%)",
                backgroundColor: "rgba(255,255,255,0.15)",
              }}
            />
            {/* Playhead line */}
            <div
              className="absolute top-[-4px] bottom-[-4px] w-1 rounded-sm bg-white pointer-events-none"
              style={{ left: `${playheadPct}%`, transform: "translateX(-50%)" }}
            />
            {/* Triangle cap */}
            <div
              className="absolute pointer-events-none"
              style={{
                left: `${playheadPct}%`,
                top: "-8px",
                transform: "translateX(-50%)",
                width: 0,
                height: 0,
                borderLeft: "5px solid transparent",
                borderRight: "5px solid transparent",
                borderTop: "6px solid white",
              }}
            />
          </>
        )}
      </div>

      {/* Time labels */}
      <div className="mt-1.5 flex items-center justify-between text-[10px] text-[var(--text-secondary)]">
        <span>{oldestTime}</span>
        {selectedIndex >= 0 && (
          <span className="text-[var(--app-accent)] font-medium">
            {formatTime(chronological[selectedIndex].timestamp)}
            {chronological[selectedIndex].appName && (
              <> · {chronological[selectedIndex].appName}</>
            )}
          </span>
        )}
        <span>{newestTime}</span>
      </div>
    </div>
  );
}
