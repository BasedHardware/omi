import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useRewindStore, type Screenshot } from "../../stores/rewindStore";
import { getScreenshotImage } from "../../services/rewind";
import { Search, X, Circle, Square, Clock, Monitor, FileText, ChevronDown, ChevronUp, Loader2, Trash2, Sparkles, Type } from "lucide-react";

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
    cancelImageLoad,
  } = useRewindStore();

  // When the user navigates away from any Aura tab (Rewind/Focus), cancel the
  // in-flight eager image decode so it doesn't compete with the next screen's
  // first paint. The page itself stays mounted (route keep-alive) so we use
  // location instead of an unmount cleanup.
  const { pathname } = useLocation();
  const isRewindRoute =
    pathname === "/aura" || pathname === "/rewind" || pathname === "/focus";
  useEffect(() => {
    if (!isRewindRoute) cancelImageLoad();
  }, [isRewindRoute, cancelImageLoad]);

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

  // When search results arrive, auto-select the top hit so the viewer shows
  // *something* the user can orient around (otherwise they get a stale image
  // from before the search).
  useEffect(() => {
    if (!searchQuery || searchResults.length === 0) return;
    const inResults = searchResults.some((r) => r.id === selectedScreenshot?.id);
    if (!inResults) {
      void selectScreenshot(searchResults[0].id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery, searchResults]);

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
            placeholder="Search words or describe what you saw…"
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
        {/* Search result count — split by match type so the user sees why something matched. */}
        {searchQuery && !isSearching && (
          <div className="mt-1.5 flex items-center gap-3 pl-1 text-xs text-[var(--text-secondary)]">
            {searchResults.length === 0 ? (
              <span>No matches for &ldquo;{searchQuery}&rdquo;</span>
            ) : (
              <>
                <span>
                  {searchResults.length} result
                  {searchResults.length === 1 ? "" : "s"}
                </span>
                {(() => {
                  const keyword = searchResults.filter((r) => r.matchType === "keyword").length;
                  const semantic = searchResults.filter((r) => r.matchType === "semantic").length;
                  return (
                    <span className="flex items-center gap-2 text-[var(--text-secondary)]">
                      {keyword > 0 && (
                        <span className="inline-flex items-center gap-1">
                          <Type className="h-3 w-3" /> {keyword} text
                        </span>
                      )}
                      {semantic > 0 && (
                        <span className="inline-flex items-center gap-1">
                          <Sparkles className="h-3 w-3" /> {semantic} meaning
                        </span>
                      )}
                    </span>
                  );
                })()}
              </>
            )}
          </div>
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
                      // The delete button sits on the dark gradient overlay at the top
                      // of the selected screenshot — bg-white/20 is correct in both themes.
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
        ) : searchQuery && !isSearching && searchResults.length === 0 ? (
          /* No search matches */
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-[var(--bg-secondary)] border border-[var(--app-border)]">
              <Search className="h-8 w-8 text-[var(--text-secondary)]" />
            </div>
            <h3 className="text-lg font-medium text-[var(--text-primary)]">
              No matches for &ldquo;{searchQuery}&rdquo;
            </h3>
            <p className="max-w-sm text-sm text-[var(--text-secondary)]">
              Try different words, or describe what was on screen (e.g.
              &ldquo;spreadsheet&rdquo;, &ldquo;calendar invite&rdquo;).
            </p>
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

      {/* Bottom strip: search results when searching, timeline otherwise. */}
      {searchQuery ? (
        searchResults.length > 0 && (
          <SearchResultsStrip
            results={searchResults}
            selectedId={selectedScreenshot?.id ?? null}
            query={searchQuery}
            onSelect={handleThumbnailClick}
            formatTime={formatTime}
          />
        )
      ) : (
        displayedScreenshots.length > 0 && (
          <TimelineBar
            screenshots={displayedScreenshots}
            selectedId={selectedScreenshot?.id ?? null}
            onSelect={handleThumbnailClick}
            formatTime={formatTime}
          />
        )
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
        className="relative h-8 w-full cursor-pointer rounded overflow-hidden select-none bg-foreground/10"
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
            className="absolute top-0 h-full w-[2px] bg-foreground/50 pointer-events-none"
            style={{ left: `${hoverPct}%`, transform: "translateX(-50%)" }}
          />
        )}

        {/* Playhead */}
        {playheadPct !== null && (
          <>
            {/* Glow */}
            <div
              className="absolute top-[-2px] bottom-[-2px] w-2 rounded pointer-events-none bg-foreground/15"
              style={{
                left: `${playheadPct}%`,
                transform: "translateX(-50%)",
              }}
            />
            {/* Playhead line */}
            <div
              className="absolute top-[-4px] bottom-[-4px] w-1 rounded-sm bg-foreground pointer-events-none"
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
                borderTop: "6px solid var(--text-primary)",
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

// ---------------------------------------------------------------------------
// SearchResultsStrip — horizontal thumbnails ranked by match, shown when
// the user is searching. Each card shows an OCR snippet with the query
// highlighted plus a "Text" / "Meaning" badge, so the user always knows
// *why* something is a match.
// ---------------------------------------------------------------------------

interface SearchResultsStripProps {
  results: Screenshot[];
  selectedId: string | null;
  query: string;
  onSelect: (id: string) => void;
  formatTime: (ts: string) => string;
}

function SearchResultsStrip({
  results,
  selectedId,
  query,
  onSelect,
  formatTime,
}: SearchResultsStripProps) {
  return (
    <div className="shrink-0 border-t border-[var(--app-border)] bg-[var(--bg-secondary)] px-4 py-3">
      <div className="flex gap-2 overflow-x-auto pb-1">
        {results.map((s) => (
          <SearchResultCard
            key={s.id}
            screenshot={s}
            query={query}
            selected={selectedId === s.id}
            onSelect={() => onSelect(s.id)}
            formatTime={formatTime}
          />
        ))}
      </div>
    </div>
  );
}

interface SearchResultCardProps {
  screenshot: Screenshot;
  query: string;
  selected: boolean;
  onSelect: () => void;
  formatTime: (ts: string) => string;
}

function SearchResultCard({
  screenshot: s,
  query,
  selected,
  onSelect,
  formatTime,
}: SearchResultCardProps) {
  // Lazy-load the thumbnail when the card first renders. Cards stay cheap
  // because the DB query returns metadata only.
  const [thumb, setThumb] = useState<string | null>(s.data || null);
  useEffect(() => {
    if (thumb || s.dbId <= 0) return;
    let cancelled = false;
    void (async () => {
      try {
        const data = await getScreenshotImage(s.dbId);
        if (!cancelled && data) setThumb(data);
      } catch {
        /* ignore — card still renders metadata */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [s.dbId, thumb]);

  const snippet = useMemo(
    () => buildSnippet(s.ocrText, query, 140),
    [s.ocrText, query],
  );

  return (
    <button
      onClick={onSelect}
      className={`shrink-0 w-56 rounded-lg border p-2 text-left transition-colors ${
        selected
          ? "border-[var(--app-accent)] bg-[var(--bg-tertiary)]"
          : "border-[var(--app-border)] bg-[var(--bg-primary)] hover:bg-[var(--bg-tertiary)]"
      }`}
    >
      {/* Thumbnail */}
      <div className="relative mb-2 aspect-video w-full overflow-hidden rounded bg-black/30">
        {thumb ? (
          <img
            src={`data:image/jpeg;base64,${thumb}`}
            alt={s.windowTitle || s.appName}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <Loader2 className="h-4 w-4 text-[var(--text-secondary)] animate-spin" />
          </div>
        )}
        {/* Match-type badge */}
        {s.matchType && (
          <div
            className={`absolute top-1.5 right-1.5 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium ${
              s.matchType === "keyword"
                ? "bg-sky-500/20 text-sky-200"
                : "bg-violet-500/20 text-violet-200"
            }`}
            title={
              s.matchType === "keyword"
                ? "Matched your words in on-screen text"
                : `Matched by meaning${s.matchScore != null ? ` (${(s.matchScore * 100).toFixed(0)}%)` : ""}`
            }
          >
            {s.matchType === "keyword" ? (
              <>
                <Type className="h-2.5 w-2.5" />
                Text
              </>
            ) : (
              <>
                <Sparkles className="h-2.5 w-2.5" />
                Meaning
              </>
            )}
          </div>
        )}
      </div>

      {/* Meta line */}
      <div className="mb-1 flex items-center justify-between gap-2 text-xs">
        <span className="truncate font-medium text-[var(--text-primary)]">
          {s.appName || "Unknown"}
        </span>
        <span className="shrink-0 text-[var(--text-secondary)]">
          {formatTime(s.timestamp)}
        </span>
      </div>

      {/* OCR snippet with query highlighted (keyword matches only — semantic
          hits don't necessarily contain the query literally). */}
      {snippet && (
        <p className="line-clamp-2 text-[11px] leading-snug text-[var(--text-secondary)]">
          {renderHighlighted(snippet, query)}
        </p>
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Snippet + highlight helpers
// ---------------------------------------------------------------------------

/** Build a ~N-char snippet centered on the first occurrence of the query. */
function buildSnippet(
  text: string | undefined,
  query: string,
  maxLen: number,
): string | null {
  if (!text) return null;
  const q = query.trim().toLowerCase();
  if (!q) return text.slice(0, maxLen);
  const idx = text.toLowerCase().indexOf(q);
  if (idx < 0) {
    // Semantic hit with no literal match — just return the head of the OCR.
    return text.slice(0, maxLen).trim();
  }
  const half = Math.floor((maxLen - q.length) / 2);
  const start = Math.max(0, idx - half);
  const end = Math.min(text.length, start + maxLen);
  return (start > 0 ? "…" : "") + text.slice(start, end).trim() + (end < text.length ? "…" : "");
}

/** Render a snippet with case-insensitive matches of `query` bolded. */
function renderHighlighted(snippet: string, query: string): React.ReactNode {
  const q = query.trim();
  if (!q) return snippet;
  const parts: React.ReactNode[] = [];
  const lower = snippet.toLowerCase();
  const qLower = q.toLowerCase();
  let cursor = 0;
  let next = lower.indexOf(qLower, cursor);
  let key = 0;
  while (next >= 0) {
    if (next > cursor) parts.push(snippet.slice(cursor, next));
    parts.push(
      <mark
        key={`m${key++}`}
        className="rounded bg-yellow-400/30 px-0.5 font-semibold text-[var(--text-primary)]"
      >
        {snippet.slice(next, next + q.length)}
      </mark>,
    );
    cursor = next + q.length;
    next = lower.indexOf(qLower, cursor);
  }
  if (cursor < snippet.length) parts.push(snippet.slice(cursor));
  return parts;
}
