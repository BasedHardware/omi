import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { invoke } from "@tauri-apps/api/core";
import {
  Monitor,
  Eye,
  EyeOff,
  Activity,
  AlertTriangle,
  BarChart3,
  Loader2,
  Send,
} from "lucide-react";
import { RewindPage } from "../rewind/RewindPage";
import { FocusPage } from "../focus/FocusPage";
import {
  useFocusStore,
  useFocusStats,
  useTodaySessions,
} from "@/stores/focusStore";
import {
  PageHeader,
  PageHeaderFilter,
  PageHeaderFilters,
} from "../ui/page-header";

type AuraTab = "rewind" | "focus";

const TABS: { id: AuraTab; label: string; icon: typeof Monitor }[] = [
  { id: "rewind", label: "Rewind", icon: Monitor },
  { id: "focus", label: "Focus", icon: Eye },
];

export function AuraPage() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [tab, setTab] = useState<AuraTab>(pathname === "/focus" ? "focus" : "rewind");

  useEffect(() => {
    if (pathname === "/focus" && tab !== "focus") setTab("focus");
    else if (pathname === "/rewind" && tab !== "rewind") setTab("rewind");
  }, [pathname, tab]);

  const selectTab = (next: AuraTab) => {
    setTab(next);
    const targetPath = next === "focus" ? "/focus" : "/rewind";
    if (pathname !== targetPath) navigate(targetPath);
  };

  return (
    <div className="flex h-full flex-col">
      <AuraStatusStrip />
      <PageHeader title="Rewind">
        <PageHeaderFilters>
          {TABS.map((t) => {
            const Icon = t.icon;
            return (
              <PageHeaderFilter
                key={t.id}
                active={tab === t.id}
                onClick={() => selectTab(t.id)}
                icon={<Icon className="size-3.5" />}
              >
                {t.label}
              </PageHeaderFilter>
            );
          })}
        </PageHeaderFilters>
      </PageHeader>
      <div className="min-h-0 flex-1 overflow-hidden">
        {tab === "rewind" ? <RewindPage /> : <FocusPage />}
      </div>
    </div>
  );
}

function AuraStatusStrip() {
  const focusEnabled = useFocusStore((s) => s.focusEnabled);
  const currentStatus = useFocusStore((s) => s.currentStatus);
  const isAnalyzing = useFocusStore((s) => s.isAnalyzing);
  const detectedAppName = useFocusStore((s) => s.detectedAppName);
  const errorMessage: string | null = null;
  const triggerTestNotification = async () => {
    console.log("[AuraPage] Test notification button CLICKED");
    try {
      const result = await invoke("show_notification_alert", {
        title: "Focus",
        body: "Test notification — the dedicated notification bar is working.",
      });
      console.log("[AuraPage] show_notification_alert returned", result);
    } catch (err) {
      console.error("[AuraPage] show_notification_alert failed", err);
    }
  };
  const stats = useFocusStats();
  const todaySessions = useTodaySessions();

  const hasData = focusEnabled && todaySessions.length > 0;

  return (
    <div className="flex shrink-0 items-center gap-4 border-b border-border/50 bg-secondary/20 px-4 py-2.5">
      <FocusStatusPill
        focusEnabled={focusEnabled}
        currentStatus={currentStatus}
        isAnalyzing={isAnalyzing}
        detectedAppName={detectedAppName}
        errorMessage={errorMessage}
      />

      <button
        type="button"
        onClick={() => void triggerTestNotification()}
        className="flex items-center gap-1.5 rounded-full border border-border/60 bg-background/40 px-2.5 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        title="Send a test OS notification to verify alerts work"
      >
        <Send className="size-3" />
        Test notification
      </button>

      {hasData ? (
        <div className="ml-auto flex items-center gap-4">
          <Stat
            icon={<Eye className="size-3" />}
            label="Focus"
            value={`${stats.focusMinutes}m`}
            color="text-green-400"
          />
          <Stat
            icon={<AlertTriangle className="size-3" />}
            label="Distracted"
            value={`${stats.distractedMinutes}m`}
            color="text-red-400"
          />
          <Stat
            icon={<BarChart3 className="size-3" />}
            label="Rate"
            value={`${stats.focusRate}%`}
            color="text-blue-400"
          />
          <Stat
            icon={<Activity className="size-3" />}
            label="Sessions"
            value={`${stats.sessionCount}`}
            color="text-purple-400"
          />
        </div>
      ) : focusEnabled ? (
        <span className="ml-auto text-xs text-muted-foreground">
          Collecting data…
        </span>
      ) : null}
    </div>
  );
}

function FocusStatusPill({
  focusEnabled,
  currentStatus,
  isAnalyzing,
  detectedAppName,
  errorMessage,
}: {
  focusEnabled: boolean;
  currentStatus: string | null;
  isAnalyzing: boolean;
  detectedAppName: string | null;
  errorMessage: string | null;
}) {
  if (errorMessage) {
    return (
      <span
        className="flex items-center gap-1.5 rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-400"
        title={errorMessage}
      >
        <AlertTriangle className="size-3" />
        Rewind error
      </span>
    );
  }

  if (!focusEnabled) {
    return (
      <span className="flex items-center gap-1.5 rounded-full border border-border/60 bg-background/40 px-2.5 py-1 text-xs text-muted-foreground">
        <EyeOff className="size-3" />
        Rewind off
      </span>
    );
  }

  if (isAnalyzing) {
    return (
      <span className="flex items-center gap-1.5 rounded-full border border-blue-500/30 bg-blue-500/10 px-2.5 py-1 text-xs font-medium text-blue-400">
        <Loader2 className="size-3 animate-spin" />
        Analyzing{detectedAppName ? ` · ${detectedAppName}` : ""}
      </span>
    );
  }

  if (currentStatus === "focused") {
    return (
      <span className="flex items-center gap-1.5 rounded-full border border-green-500/30 bg-green-500/10 px-2.5 py-1 text-xs font-medium text-green-400">
        <span className="relative flex size-2">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-green-500/60" />
          <span className="relative inline-flex size-2 rounded-full bg-green-500" />
        </span>
        Focused{detectedAppName ? ` · ${detectedAppName}` : ""}
      </span>
    );
  }

  if (currentStatus === "distracted") {
    return (
      <span className="flex items-center gap-1.5 rounded-full border border-red-500/30 bg-red-500/10 px-2.5 py-1 text-xs font-medium text-red-400">
        <AlertTriangle className="size-3" />
        Distracted{detectedAppName ? ` · ${detectedAppName}` : ""}
      </span>
    );
  }

  return (
    <span className="flex items-center gap-1.5 rounded-full border border-border/60 bg-background/40 px-2.5 py-1 text-xs text-muted-foreground">
      <Eye className="size-3" />
      Rewind on
    </span>
  );
}

function Stat({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className={color}>{icon}</span>
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-xs font-semibold tabular-nums text-foreground">
        {value}
      </span>
    </div>
  );
}
