/**
 * Focus Page — real-time focus monitoring dashboard.
 *
 * Ported from Swift: FocusPage.swift + FocusViewModel
 *
 * Sections:
 * - Status banner with live countdown (delay, cooldown, analyzing, focused/distracted)
 * - Today's stats grid (focus time, distracted time, focus rate, sessions)
 * - Top distractions list
 * - Searchable session history with delete
 */

import { useEffect, useMemo, useState } from "react";
import {
  Eye,
  EyeOff,
  Clock,
  Pause,
  Loader2,
  Search,
  X,
  Trash2,
  Activity,
  BarChart3,
  AlertTriangle,
  Bell,
  BellOff,
} from "lucide-react";
import {
  useFocusStore,
  useFocusStats,
  useTodaySessions,
  useAllSessions,
} from "@/stores/focusStore";
import type { FocusSession } from "@/stores/focusStore";

// ---------------------------------------------------------------------------
// Countdown hook — updates every second while active
// ---------------------------------------------------------------------------

function useCountdown(endTime: Date | null): number {
  const [remaining, setRemaining] = useState(0);

  useEffect(() => {
    if (!endTime) {
      setRemaining(0);
      return;
    }

    const tick = () => {
      const ms = endTime.getTime() - Date.now();
      setRemaining(Math.max(0, Math.ceil(ms / 1000)));
    };

    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [endTime]);

  return remaining;
}

function formatCountdown(seconds: number): string {
  if (seconds <= 0) return "0s";
  if (seconds < 60) return `${seconds}s`;
  const min = Math.floor(seconds / 60);
  const sec = seconds % 60;
  return sec > 0 ? `${min}m ${sec}s` : `${min}m`;
}

function formatDuration(totalSeconds: number): string {
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const hours = Math.floor(totalSeconds / 3600);
  const min = Math.floor((totalSeconds % 3600) / 60);
  if (hours > 0) return min > 0 ? `${hours}h ${min}m` : `${hours}h`;
  return `${min}m`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function FocusPage() {
  const {
    focusEnabled,
    currentStatus,
    lastAnalysis,
    detectedAppName,
    delayEndTime,
    cooldownEndTime,
    isAnalyzing,
    notificationsEnabled,
    sessions,
    toggleFocus,
    toggleNotifications,
    deleteSession,
    clearSessions,
  } = useFocusStore();

  const stats = useFocusStats();
  const todaySessions = useTodaySessions();
  const allSessions = useAllSessions();

  const [showAllSessions, setShowAllSessions] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const delayRemaining = useCountdown(delayEndTime);
  const cooldownRemaining = useCountdown(cooldownEndTime);

  // Filter sessions based on search and toggle
  const displayedSessions = useMemo(() => {
    const source = showAllSessions ? allSessions : todaySessions;
    if (!searchQuery.trim()) return source;
    const q = searchQuery.toLowerCase();
    return source.filter(
      (s) =>
        s.app_or_site.toLowerCase().includes(q) ||
        s.description.toLowerCase().includes(q) ||
        (s.message && s.message.toLowerCase().includes(q)),
    );
  }, [showAllSessions, allSessions, todaySessions, searchQuery]);

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-6 pt-5 pb-4 shrink-0">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-semibold text-[var(--text-primary)]">
            Focus
          </h2>
          {focusEnabled && (
            <div className="flex items-center gap-1.5">
              <span className="relative flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-500 opacity-75" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-green-500" />
              </span>
              <span className="text-xs font-medium text-green-400">
                Active
              </span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={toggleNotifications}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors border ${
              notificationsEnabled
                ? "text-[var(--text-secondary)] border-[var(--app-border)] hover:bg-[var(--bg-tertiary)]"
                : "text-yellow-400 border-yellow-500/20 hover:bg-yellow-500/10"
            }`}
            title={
              notificationsEnabled
                ? "Notifications on"
                : "Notifications muted"
            }
          >
            {notificationsEnabled ? (
              <Bell className="h-3.5 w-3.5" />
            ) : (
              <BellOff className="h-3.5 w-3.5" />
            )}
          </button>
          <button
            onClick={toggleFocus}
            className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              focusEnabled
                ? "bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/30"
                : "bg-[var(--app-accent)] text-white hover:bg-[var(--app-accent-hover)]"
            }`}
          >
            {focusEnabled ? (
              <>
                <EyeOff className="h-3.5 w-3.5" />
                Stop Monitoring
              </>
            ) : (
              <>
                <Eye className="h-3.5 w-3.5" />
                Start Monitoring
              </>
            )}
          </button>
        </div>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto px-6 pb-6 min-h-0 space-y-5">
        {/* Status Banner */}
        <StatusBanner
          focusEnabled={focusEnabled}
          currentStatus={currentStatus}
          lastAnalysis={lastAnalysis}
          detectedAppName={detectedAppName}
          delayRemaining={delayRemaining}
          cooldownRemaining={cooldownRemaining}
          isAnalyzing={isAnalyzing}
          delayEndTime={delayEndTime}
          cooldownEndTime={cooldownEndTime}
        />

        {/* Stats Grid */}
        {focusEnabled && todaySessions.length > 0 && (
          <div className="grid grid-cols-4 gap-3">
            <StatCard
              label="Focus Time"
              value={`${stats.focusMinutes}m`}
              icon={<Eye className="h-4 w-4" />}
              color="text-green-400"
            />
            <StatCard
              label="Distracted"
              value={`${stats.distractedMinutes}m`}
              icon={<AlertTriangle className="h-4 w-4" />}
              color="text-red-400"
            />
            <StatCard
              label="Focus Rate"
              value={`${stats.focusRate}%`}
              icon={<BarChart3 className="h-4 w-4" />}
              color="text-[var(--app-accent)]"
            />
            <StatCard
              label="Sessions"
              value={`${stats.sessionCount}`}
              icon={<Activity className="h-4 w-4" />}
              color="text-purple-400"
            />
          </div>
        )}

        {/* Top Distractions */}
        {focusEnabled && stats.topDistractions.length > 0 && (
          <div className="rounded-xl border border-[var(--app-border)] bg-[var(--bg-secondary)] p-4">
            <h3 className="text-sm font-medium text-[var(--text-primary)] mb-3">
              Top Distractions Today
            </h3>
            <div className="space-y-2">
              {stats.topDistractions.map((d) => (
                <div
                  key={d.app}
                  className="flex items-center justify-between text-sm"
                >
                  <span className="text-[var(--text-primary)] truncate flex-1">
                    {d.app}
                  </span>
                  <div className="flex items-center gap-3 text-[var(--text-secondary)] shrink-0">
                    <span className="text-xs">
                      {d.count}x
                    </span>
                    <span className="text-xs w-14 text-right">
                      {formatDuration(d.totalSeconds)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Session History */}
        <div className="rounded-xl border border-[var(--app-border)] bg-[var(--bg-secondary)]">
          {/* History header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--app-border)]">
            <div className="flex items-center gap-3">
              <h3 className="text-sm font-medium text-[var(--text-primary)]">
                Session History
              </h3>
              <div className="flex rounded-md border border-[var(--app-border)] overflow-hidden">
                <button
                  onClick={() => setShowAllSessions(false)}
                  className={`px-2.5 py-1 text-xs font-medium transition-colors ${
                    !showAllSessions
                      ? "bg-[var(--app-accent)] text-white"
                      : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  Today
                </button>
                <button
                  onClick={() => setShowAllSessions(true)}
                  className={`px-2.5 py-1 text-xs font-medium transition-colors ${
                    showAllSessions
                      ? "bg-[var(--app-accent)] text-white"
                      : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  All
                </button>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {sessions.length > 0 && (
                <button
                  onClick={clearSessions}
                  className="flex items-center gap-1 px-2 py-1 text-xs text-red-400 hover:bg-red-500/10 rounded transition-colors"
                >
                  <Trash2 className="h-3 w-3" />
                  Clear
                </button>
              )}
            </div>
          </div>

          {/* Search */}
          <div className="px-4 py-2 border-b border-[var(--app-border)]">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-secondary)]" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search sessions..."
                className="w-full rounded-md border border-[var(--app-border)] bg-[var(--bg-tertiary)] py-1.5 pl-8 pr-8 text-xs text-[var(--text-primary)] outline-none placeholder:text-[var(--text-secondary)] transition-colors focus:border-[var(--app-accent)]"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          </div>

          {/* Session list */}
          <div className="max-h-[400px] overflow-y-auto">
            {displayedSessions.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-[var(--text-secondary)]">
                {!focusEnabled
                  ? "Start monitoring to see your focus sessions."
                  : searchQuery
                    ? "No sessions match your search."
                    : "No sessions yet. Focus data will appear here."}
              </div>
            ) : (
              displayedSessions.map((session) => (
                <SessionRow
                  key={session.id}
                  session={session}
                  onDelete={() => deleteSession(session.id)}
                />
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Status Banner
// ---------------------------------------------------------------------------

function StatusBanner({
  focusEnabled,
  currentStatus,
  lastAnalysis,
  detectedAppName,
  delayRemaining,
  cooldownRemaining,
  isAnalyzing,
  delayEndTime,
  cooldownEndTime,
}: {
  focusEnabled: boolean;
  currentStatus: string | null;
  lastAnalysis: { app_or_site: string; message?: string } | null;
  detectedAppName: string | null;
  delayRemaining: number;
  cooldownRemaining: number;
  isAnalyzing: boolean;
  delayEndTime: Date | null;
  cooldownEndTime: Date | null;
}) {
  if (!focusEnabled) {
    return (
      <div className="rounded-xl border border-[var(--app-border)] bg-[var(--bg-secondary)] p-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center h-10 w-10 rounded-full bg-[var(--bg-tertiary)]">
            <EyeOff className="h-5 w-5 text-[var(--text-secondary)]" />
          </div>
          <div>
            <p className="text-sm font-medium text-[var(--text-primary)]">
              Focus Monitoring Off
            </p>
            <p className="text-xs text-[var(--text-secondary)]">
              Start monitoring to track your focus in real time.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Priority: delay > cooldown > analyzing > status
  if (delayEndTime && delayRemaining > 0) {
    return (
      <BannerCard
        icon={<Clock className="h-5 w-5" />}
        title="Waiting to Analyze"
        subtitle={detectedAppName ?? "Switched apps"}
        detail={`Analyzing in ${formatCountdown(delayRemaining)}`}
        color="blue"
      />
    );
  }

  if (cooldownEndTime && cooldownRemaining > 0) {
    return (
      <BannerCard
        icon={<Pause className="h-5 w-5" />}
        title="Cooldown Active"
        subtitle={lastAnalysis?.app_or_site ?? ""}
        detail={`Next check in ${formatCountdown(cooldownRemaining)}`}
        color="orange"
      />
    );
  }

  if (isAnalyzing && !currentStatus) {
    return (
      <BannerCard
        icon={<Loader2 className="h-5 w-5 animate-spin" />}
        title="Analyzing..."
        subtitle={detectedAppName ?? "Detecting app"}
        detail=""
        color="gray"
      />
    );
  }

  if (currentStatus === "focused") {
    return (
      <BannerCard
        icon={<Eye className="h-5 w-5" />}
        title="Focused"
        subtitle={lastAnalysis?.app_or_site ?? ""}
        detail={lastAnalysis?.message ?? "You're on track!"}
        color="green"
      />
    );
  }

  if (currentStatus === "distracted") {
    return (
      <BannerCard
        icon={<EyeOff className="h-5 w-5" />}
        title="Distracted"
        subtitle={lastAnalysis?.app_or_site ?? ""}
        detail={lastAnalysis?.message ?? "Time to refocus!"}
        color="red"
      />
    );
  }

  // Default: monitoring started but no analysis yet
  return (
    <BannerCard
      icon={<Eye className="h-5 w-5" />}
      title="Monitoring"
      subtitle={detectedAppName ?? "Waiting for first capture..."}
      detail=""
      color="gray"
    />
  );
}

// ---------------------------------------------------------------------------
// Banner Card
// ---------------------------------------------------------------------------

const BANNER_COLORS = {
  blue: {
    bg: "bg-blue-500/10",
    border: "border-blue-500/30",
    icon: "bg-blue-500/20 text-blue-400",
    title: "text-blue-300",
  },
  orange: {
    bg: "bg-orange-500/10",
    border: "border-orange-500/30",
    icon: "bg-orange-500/20 text-orange-400",
    title: "text-orange-300",
  },
  green: {
    bg: "bg-green-500/10",
    border: "border-green-500/30",
    icon: "bg-green-500/20 text-green-400",
    title: "text-green-300",
  },
  red: {
    bg: "bg-red-500/10",
    border: "border-red-500/30",
    icon: "bg-red-500/20 text-red-400",
    title: "text-red-300",
  },
  gray: {
    bg: "bg-[var(--bg-secondary)]",
    border: "border-[var(--app-border)]",
    icon: "bg-[var(--bg-tertiary)] text-[var(--text-secondary)]",
    title: "text-[var(--text-primary)]",
  },
};

function BannerCard({
  icon,
  title,
  subtitle,
  detail,
  color,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  detail: string;
  color: keyof typeof BANNER_COLORS;
}) {
  const c = BANNER_COLORS[color];

  return (
    <div className={`rounded-xl border ${c.border} ${c.bg} p-4`}>
      <div className="flex items-center gap-3">
        <div
          className={`flex items-center justify-center h-10 w-10 rounded-full ${c.icon}`}
        >
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className={`text-sm font-medium ${c.title}`}>{title}</p>
            {subtitle && (
              <span className="text-xs text-[var(--text-secondary)] truncate">
                {subtitle}
              </span>
            )}
          </div>
          {detail && (
            <p className="text-xs text-[var(--text-secondary)] mt-0.5">
              {detail}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stat Card
// ---------------------------------------------------------------------------

function StatCard({
  label,
  value,
  icon,
  color,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  color: string;
}) {
  return (
    <div className="rounded-xl border border-[var(--app-border)] bg-[var(--bg-secondary)] p-3">
      <div className={`flex items-center gap-1.5 mb-1.5 ${color}`}>
        {icon}
        <span className="text-xs font-medium text-[var(--text-secondary)]">
          {label}
        </span>
      </div>
      <p className="text-lg font-semibold text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Session Row
// ---------------------------------------------------------------------------

function SessionRow({
  session,
  onDelete,
}: {
  session: FocusSession;
  onDelete: () => void;
}) {
  const [hovered, setHovered] = useState(false);

  const timeStr = new Date(session.created_at).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  const durationStr =
    session.duration_seconds !== null
      ? formatDuration(session.duration_seconds)
      : "";

  return (
    <div
      className="flex items-start gap-3 px-4 py-2.5 border-b border-[var(--app-border)] last:border-b-0 hover:bg-[var(--bg-tertiary)] transition-colors"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Status dot */}
      <div className="mt-1.5 shrink-0">
        <span
          className={`block h-2.5 w-2.5 rounded-full ${
            session.status === "focused" ? "bg-green-500" : "bg-red-500"
          }`}
        />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-[var(--text-primary)] truncate">
            {session.app_or_site}
          </span>
          {durationStr && (
            <span className="text-xs text-[var(--text-secondary)] shrink-0">
              {durationStr}
            </span>
          )}
        </div>
        <p className="text-xs text-[var(--text-secondary)] truncate mt-0.5">
          {session.description}
        </p>
        {session.message && (
          <p className="text-xs text-[var(--text-secondary)] opacity-70 truncate mt-0.5 italic">
            {session.message}
          </p>
        )}
      </div>

      {/* Time + delete */}
      <div className="flex items-center gap-2 shrink-0">
        <span className="text-xs text-[var(--text-secondary)]">{timeStr}</span>
        {hovered && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            className="flex items-center justify-center h-5 w-5 rounded hover:bg-red-500/20 transition-colors"
          >
            <Trash2 className="h-3 w-3 text-red-400" />
          </button>
        )}
      </div>
    </div>
  );
}
