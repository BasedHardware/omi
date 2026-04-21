import { memo, useEffect, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { motion, useMotionValue, useTransform, animate } from "motion/react";
import {
  Home,
  MessageSquare,
  AudioLines,
  ListTodo,
  Brain,
  Lightbulb,
  AudioWaveform,
  Mic,
  MicOff,
  Rewind,
  Settings,
  ChevronLeft,
  ChevronRight,
  LogOut,
  LayoutGrid,
  ChevronsUpDown,
  Target,
  Bluetooth,
} from "lucide-react";
import { useAuthStore } from "../../stores/authStore";
import { useSidebarStore } from "../../stores/sidebarStore";
import { useFocusStore } from "../../stores/focusStore";
import { useRewindStore } from "../../stores/rewindStore";
import { useAudioStore } from "../../stores/audioStore";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { Switch } from "../ui/switch";
import { TRANSCRIPTION_LANGUAGES } from "../../stores/audioStore";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import {
  OrbIndicator,
  type OrbVariant,
  type PersonaState,
} from "../feedback/OrbIndicator";
import { useElapsed } from "../../hooks/useElapsed";

const navItems = [
  { to: "/dashboard", label: "Home", icon: Home },
  { to: "/chat", label: "Chat", icon: MessageSquare },
  { to: "/meetings", label: "Meetings", icon: AudioLines },
  { to: "/tasks", label: "Tasks", icon: ListTodo },
  { to: "/goals", label: "Goals", icon: Target },
  { to: "/memories", label: "Memories", icon: Brain },
  { to: "/insights", label: "Insights", icon: Lightbulb },
  { to: "/whispr", label: "Whispr", icon: AudioWaveform },
  { to: "/apps", label: "Apps", icon: LayoutGrid },
  { to: "/devices", label: "Devices", icon: Bluetooth },
  { to: "/rewind", label: "Rewind", icon: Rewind },
];

const EXPANDED = 220;
const COLLAPSED = 52;
const ICON_PL = 10;

export function Sidebar() {
  const { userEmail, signOut } = useAuthStore();
  const { isCollapsed, toggle } = useSidebarStore();
  // Pulled with a narrow selector so only this component re-renders when
  // recording starts / stops — the whole sidebar doesn't churn.
  const isRecordingForNav = useAudioStore((s) => s.isRecording);

  // Single motion value drives everything — 0 = collapsed, 1 = expanded.
  // Width animation pushes the main content; reflows are scoped by
  // `contain: layout paint` on `.main-content` so they don't cascade
  // into mounted routes (KeepAlivePane wraps each in its own block).
  const progress = useMotionValue(isCollapsed ? 0 : 1);
  const width = useTransform(progress, [0, 1], [COLLAPSED, EXPANDED]);
  const textOpacity = useTransform(progress, [0, 0.5, 1], [0, 0, 1]);

  useEffect(() => {
    // Snappy easeOut — front-loaded so the sidebar reaches its final
    // size quickly and any reflow cost concentrates in the first frames.
    const opts = { duration: 0.22, ease: [0.32, 0.72, 0, 1] as const };
    animate(progress, isCollapsed ? 0 : 1, opts);
  }, [isCollapsed, progress]);

  // Cmd+B / Ctrl+B
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "b" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        toggle();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [toggle]);

  return (
    <motion.div
      className="group/sidebar relative flex flex-shrink-0"
      style={{ width }}
    >
      <aside
        className="flex h-full w-full flex-col overflow-hidden bg-secondary/40"
      >
      {/* Header */}
      <div className="flex items-center h-12 flex-shrink-0 overflow-hidden px-2">
        <div className="flex items-center h-9" style={{ paddingLeft: ICON_PL }}>
          <motion.span
            className="text-sm font-semibold tracking-wide text-foreground whitespace-nowrap"
            style={{ opacity: textOpacity }}
          >
            Nooto
          </motion.span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 flex flex-col gap-0.5 px-2">
        {navItems.map((item) => (
          <NavItem
            key={item.to}
            {...item}
            isCollapsed={isCollapsed}
            textOpacity={textOpacity}
            indicator={item.to === "/meetings" && isRecordingForNav ? "recording" : null}
          />
        ))}
      </nav>

      {/* Footer */}
      <div className="mt-2 flex flex-col border-t border-border/60 bg-background/30 px-2 pb-1.5 pt-2">
        {/* Capture toggles */}
        <div className="flex flex-col gap-0.5">
          <AuraToggle isCollapsed={isCollapsed} textOpacity={textOpacity} />
          <AudioToggle isCollapsed={isCollapsed} textOpacity={textOpacity} />
        </div>

        {/* Account */}
        <div className="mt-2">
          <ProfileMenu
            email={userEmail ?? ""}
            isCollapsed={isCollapsed}
            textOpacity={textOpacity}
            onSignOut={signOut}
          />
        </div>

      </div>
      </aside>

      {/* Clickable divider — whole right edge toggles collapse */}
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            onClick={toggle}
            aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="group/divider absolute inset-y-0 -right-1 z-20 flex w-2 cursor-pointer justify-center focus-visible:outline-none"
          >
            {/* Hairline divider — thickens and brightens on hover */}
            <span className="pointer-events-none absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-border/40 transition-all group-hover/divider:w-[2px] group-hover/divider:bg-primary/60" />
            {/* Circular chevron aligned with the content header (h-12 → center at 24px) */}
            <span className="pointer-events-none absolute left-1/2 top-6 z-10 flex size-5 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-border/60 bg-background text-muted-foreground opacity-0 shadow-sm transition-all group-hover/divider:border-primary/60 group-hover/divider:bg-accent group-hover/divider:text-foreground group-hover/divider:opacity-100 group-focus-visible/divider:opacity-100 group-hover/sidebar:opacity-100">
              {isCollapsed ? (
                <ChevronRight size={12} strokeWidth={2.5} />
              ) : (
                <ChevronLeft size={12} strokeWidth={2.5} />
              )}
            </span>
          </button>
        </TooltipTrigger>
        <TooltipContent side="right" sideOffset={8}>
          {isCollapsed ? "Expand (⌘B)" : "Collapse (⌘B)"}
        </TooltipContent>
      </Tooltip>
    </motion.div>
  );
}

const NavItem = memo(function NavItem({
  to,
  label,
  icon: Icon,
  isCollapsed,
  textOpacity,
  indicator,
}: {
  to: string;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  isCollapsed: boolean;
  textOpacity: ReturnType<typeof useTransform<number, number>>;
  indicator?: "recording" | null;
}) {
  const location = useLocation();
  // "/dashboard" is the canonical home, but the router also accepts "/" as an
  // alias so we mark Home active in both cases.
  const isActive =
    to === "/"
      ? location.pathname === "/"
      : to === "/dashboard"
        ? location.pathname === "/" || location.pathname.startsWith("/dashboard")
        : location.pathname.startsWith(to);

  const row = (
    <NavLink
      to={to}
      end={to === "/"}
      className={[
        "relative flex items-center gap-3 h-8 rounded-lg transition-colors overflow-hidden",
        isActive
          ? "bg-accent text-foreground"
          : "text-muted-foreground hover:text-foreground hover:bg-accent/50",
      ].join(" ")}
      style={{ paddingLeft: ICON_PL, paddingRight: ICON_PL }}
    >
      {isCollapsed && isActive && (
        <motion.div
          layoutId="active-indicator"
          className="absolute left-[-9px] w-[3px] h-4 rounded-r-full bg-foreground"
          transition={{ type: "spring", stiffness: 500, damping: 35 }}
        />
      )}
      <Icon size={16} className="flex-shrink-0" />
      <motion.span
        className="flex-1 whitespace-nowrap text-[13px] font-medium"
        style={{ opacity: textOpacity }}
      >
        {label}
      </motion.span>
      {indicator === "recording" && (
        <span
          className="relative flex size-2 shrink-0"
          aria-label="Recording in progress"
          title="Recording in progress"
        >
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-red-500/60" />
          <span className="relative inline-flex size-2 rounded-full bg-red-500" />
        </span>
      )}
    </NavLink>
  );

  if (isCollapsed) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>{row}</TooltipTrigger>
        <TooltipContent side="right" sideOffset={8}>
          {label}
        </TooltipContent>
      </Tooltip>
    );
  }

  return row;
});

function SwitchRow({
  icon: Icon,
  label,
  tooltip,
  checked,
  onToggle,
  active,
  elapsed,
  orbVariant,
  isCollapsed,
  textOpacity,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string;
  tooltip: string;
  checked: boolean;
  onToggle: () => void;
  /** True when actually running right now (icon pulses). */
  active: boolean;
  /** Human-readable elapsed duration shown below the label. */
  elapsed?: string | null;
  /** If set, renders the animated orb in place of the Lucide icon. */
  orbVariant?: OrbVariant;
  isCollapsed: boolean;
  textOpacity: ReturnType<typeof useTransform<number, number>>;
}) {
  const orbState: PersonaState = active
    ? "listening"
    : checked
      ? "idle"
      : "asleep";

  const leading = orbVariant ? (
    <OrbIndicator
      state={orbState}
      variant={orbVariant}
      size="sm"
      orbClassName="size-5"
    />
  ) : (
    <Icon
      size={16}
      className={`flex-shrink-0 ${active ? "text-green-500" : ""}`}
    />
  );

  const row = (
    <button
      onClick={isCollapsed ? onToggle : undefined}
      className="flex items-center gap-3 h-9 rounded-lg text-muted-foreground w-full overflow-hidden transition-colors hover:bg-accent/50"
      style={{ paddingLeft: ICON_PL, paddingRight: ICON_PL }}
      aria-label={label}
      title={tooltip}
    >
      {leading}
      <motion.div
        className="flex flex-col min-w-0 flex-1 items-start"
        style={{ opacity: textOpacity }}
      >
        <span className="whitespace-nowrap text-[13px] font-medium truncate leading-tight">
          {label}
        </span>
        {elapsed && (
          <span className="whitespace-nowrap text-[10px] text-muted-foreground/70 truncate leading-tight tabular-nums">
            {elapsed}
          </span>
        )}
      </motion.div>
      <motion.div
        style={{ opacity: textOpacity, pointerEvents: isCollapsed ? "none" : "auto" }}
        onClick={(e) => e.stopPropagation()}
      >
        <Switch checked={checked} onCheckedChange={onToggle} aria-label={label} />
      </motion.div>
    </button>
  );

  if (isCollapsed) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>{row}</TooltipTrigger>
        <TooltipContent side="right" sideOffset={8}>
          {tooltip}
        </TooltipContent>
      </Tooltip>
    );
  }

  return row;
}

function AuraToggle(props: {
  isCollapsed: boolean;
  textOpacity: ReturnType<typeof useTransform<number, number>>;
}) {
  const { rewindEnabled, isCapturing, inCommercialHours, captureStartedAt, toggleRewind } =
    useRewindStore();
  const { focusEnabled, isAnalyzing, monitoringStartedAt, toggleFocus } = useFocusStore();
  const elapsed = useElapsed(captureStartedAt ?? monitoringStartedAt);

  const enabled = rewindEnabled || focusEnabled;
  const active = isCapturing || (focusEnabled && isAnalyzing);

  const onToggle = () => {
    const turnOn = !enabled;
    if (rewindEnabled !== turnOn) toggleRewind();
    if (focusEnabled !== turnOn) toggleFocus();
  };

  const tooltip = !enabled
    ? "Rewind off — turn on to capture screen + focus"
    : active
      ? `Rewind on${elapsed ? ` — ${elapsed}` : ""} • Rewind + Focus active`
      : !inCommercialHours
        ? "Rewind paused — only captures Mon-Fri 9am-5pm"
        : "Rewind on • Rewind + Focus armed";

  return (
    <SwitchRow
      icon={Rewind}
      label="Rewind"
      tooltip={tooltip}
      checked={enabled}
      onToggle={onToggle}
      active={active}
      elapsed={elapsed}
      orbVariant="halo"
      {...props}
    />
  );
}

function AudioToggle({
  isCollapsed,
  textOpacity,
}: {
  isCollapsed: boolean;
  textOpacity: ReturnType<typeof useTransform<number, number>>;
}) {
  const {
    audioEnabled,
    isRecording,
    inCommercialHours,
    recordingStartedAt,
    language,
    setLanguage,
    startAudio,
    stopAudio,
  } = useAudioStore();
  const elapsed = useElapsed(recordingStartedAt);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [pendingLang, setPendingLang] = useState(language);

  const isActive = audioEnabled || isRecording;
  const isRunning = isActive; // "running" == recording or armed
  const Icon = isActive ? MicOff : Mic;
  const label = isRunning ? "Stop meeting" : "Start a meeting";
  const tooltip = isRecording
    ? `Recording${elapsed ? ` — ${elapsed}` : ""} • click to stop`
    : audioEnabled
      ? !inCommercialHours
        ? "Paused — only captures Mon-Fri 9am-5pm • click to stop"
        : "Audio recording armed • click to stop"
      : "Pick a language and start a meeting";

  // Click: if running, stop immediately (no popover). If stopped, open the
  // popover so the user can confirm language before recording starts.
  const handleClick = () => {
    if (isRunning) {
      void stopAudio();
      useAudioStore.setState({ audioEnabled: false });
    } else {
      setPendingLang(language);
      setPopoverOpen(true);
    }
  };

  const confirmStart = async () => {
    if (pendingLang !== language) {
      await setLanguage(pendingLang);
    }
    setPopoverOpen(false);
    useAudioStore.setState({ audioEnabled: true });
    await startAudio();
  };

  const button = (
    <button
      onClick={handleClick}
      aria-label={label}
      title={tooltip}
      className={[
        "flex items-center gap-3 h-9 rounded-lg w-full overflow-hidden transition-colors",
        isRecording
          ? "bg-red-500/10 text-red-500 hover:bg-red-500/15"
          : isActive
            ? "bg-amber-500/10 text-amber-600 hover:bg-amber-500/15 dark:text-amber-400"
            : "text-muted-foreground hover:text-foreground hover:bg-accent/50",
      ].join(" ")}
      style={{ paddingLeft: ICON_PL, paddingRight: ICON_PL }}
    >
      <Icon size={16} className="flex-shrink-0" />
      <motion.div
        className="flex flex-col min-w-0 flex-1 items-start"
        style={{ opacity: textOpacity }}
      >
        <span className="whitespace-nowrap text-[13px] font-medium truncate leading-tight">
          {label}
        </span>
        {isRecording && elapsed && (
          <span className="whitespace-nowrap text-[10px] text-red-500/70 truncate leading-tight tabular-nums">
            {elapsed}
          </span>
        )}
      </motion.div>
      {isRecording && (
        <motion.span
          className="relative flex size-2 shrink-0"
          style={{ opacity: textOpacity }}
        >
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-red-500/60" />
          <span className="relative inline-flex size-2 rounded-full bg-red-500" />
        </motion.span>
      )}
    </button>
  );

  const popoverBody = (
    <PopoverContent
      side="right"
      align="start"
      sideOffset={8}
      className="w-60 p-3"
      onOpenAutoFocus={(e) => e.preventDefault()}
    >
      <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        Language
      </div>
      <div className="flex flex-col gap-1">
        {TRANSCRIPTION_LANGUAGES.map((lang) => {
          const selected = pendingLang === lang.code;
          return (
            <button
              key={lang.code}
              type="button"
              onClick={() => setPendingLang(lang.code)}
              className={[
                "flex items-center justify-between rounded-md px-2.5 py-1.5 text-[13px] transition-colors text-left",
                selected
                  ? "bg-primary/10 text-foreground"
                  : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
              ].join(" ")}
            >
              <span>{lang.label}</span>
              {selected && (
                <span className="ml-2 size-1.5 rounded-full bg-primary" />
              )}
            </button>
          );
        })}
      </div>
      <div className="mt-3 flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={() => setPopoverOpen(false)}
          className="rounded-md px-2.5 py-1.5 text-[12px] text-muted-foreground hover:bg-accent/50 hover:text-foreground transition-colors"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => void confirmStart()}
          className="rounded-md bg-primary px-3 py-1.5 text-[12px] font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          Start
        </button>
      </div>
    </PopoverContent>
  );

  // Only wrap in Popover when we actually need it (not recording). This
  // avoids stacking two `asChild` wrappers (Tooltip + Popover) on the same
  // button, which makes ref forwarding brittle.
  if (isRunning) {
    if (isCollapsed) {
      return (
        <Tooltip>
          <TooltipTrigger asChild>{button}</TooltipTrigger>
          <TooltipContent side="right" sideOffset={8}>
            {tooltip}
          </TooltipContent>
        </Tooltip>
      );
    }
    return button;
  }

  return (
    <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
      <PopoverTrigger asChild>{button}</PopoverTrigger>
      {popoverBody}
    </Popover>
  );
}

function initialsFrom(email: string): string {
  if (!email) return "?";
  const name = email.split("@")[0] ?? "";
  const parts = name.split(/[._-]+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return (name.slice(0, 2) || "?").toUpperCase();
}

function ProfileMenu({
  email,
  isCollapsed,
  textOpacity,
  onSignOut,
}: {
  email: string;
  isCollapsed: boolean;
  textOpacity: ReturnType<typeof useTransform<number, number>>;
  onSignOut: () => void | Promise<void>;
}) {
  const navigate = useNavigate();
  const initials = initialsFrom(email);

  const avatar = (
    <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-accent text-[11px] font-semibold text-foreground">
      {initials}
    </span>
  );

  const trigger = (
    <button
      className="flex h-10 w-full items-center gap-3 rounded-lg text-left transition-colors hover:bg-accent/50 overflow-hidden"
      style={{ paddingLeft: ICON_PL - 4, paddingRight: ICON_PL }}
      aria-label="Account"
    >
      {avatar}
      <motion.div
        className="flex min-w-0 flex-1 flex-col leading-tight"
        style={{ opacity: textOpacity }}
      >
        <span className="truncate whitespace-nowrap text-[12px] font-medium text-foreground">
          {email || "Account"}
        </span>
      </motion.div>
      <motion.span
        className="shrink-0 text-muted-foreground"
        style={{ opacity: textOpacity }}
      >
        <ChevronsUpDown size={14} />
      </motion.span>
    </button>
  );

  const content = (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
      <DropdownMenuContent
        side="right"
        align="end"
        sideOffset={8}
        className="min-w-[220px]"
      >
        <DropdownMenuLabel className="flex items-center gap-2 py-2">
          {avatar}
          <div className="flex min-w-0 flex-col leading-tight">
            <span className="truncate text-[12px] font-medium text-foreground">
              {email || "Account"}
            </span>
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => navigate("/settings")}>
          <Settings className="size-4" />
          Settings
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          variant="destructive"
          onSelect={() => void onSignOut()}
        >
          <LogOut className="size-4" />
          Sign Out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );

  if (isCollapsed) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="w-full">{content}</div>
        </TooltipTrigger>
        <TooltipContent side="right" sideOffset={8}>
          {email || "Account"}
        </TooltipContent>
      </Tooltip>
    );
  }

  return content;
}
