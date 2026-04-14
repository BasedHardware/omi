import { useEffect } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { motion, useMotionValue, useTransform, useSpring, animate } from "motion/react";
import {
  MessageSquare,
  AudioLines,
  ListTodo,
  Brain,
  Rewind,
  Eye,
  Mic,
  Monitor,
  Settings,
  ChevronsLeft,
  ChevronsRight,
  LogOut,
} from "lucide-react";
import { useAuthStore } from "../../stores/authStore";
import { useSidebarStore } from "../../stores/sidebarStore";
import { useFocusStore } from "../../stores/focusStore";
import { useRewindStore } from "../../stores/rewindStore";
import { useAudioStore } from "../../stores/audioStore";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";
import { Switch } from "../ui/switch";
import { useElapsed } from "../../hooks/useElapsed";

const navItems = [
  { to: "/", label: "Chat", icon: MessageSquare },
  { to: "/conversations", label: "Conversations", icon: AudioLines },
  { to: "/tasks", label: "Tasks", icon: ListTodo },
  { to: "/memories", label: "Memories", icon: Brain },
  { to: "/rewind", label: "Rewind", icon: Rewind },
  { to: "/focus", label: "Focus", icon: Eye },
  { to: "/settings", label: "Settings", icon: Settings },
];

const EXPANDED = 220;
const COLLAPSED = 52;
const ICON_PL = 10;

export function Sidebar() {
  const { userEmail, signOut } = useAuthStore();
  const { isCollapsed, toggle } = useSidebarStore();

  // Single motion value drives everything — 0 = collapsed, 1 = expanded
  const progress = useMotionValue(isCollapsed ? 0 : 1);
  const width = useTransform(progress, [0, 1], [COLLAPSED, EXPANDED]);
  const smoothWidth = useSpring(width, { stiffness: 500, damping: 35, mass: 0.6 });
  const textOpacity = useTransform(progress, [0, 0.5, 1], [0, 0, 1]);

  useEffect(() => {
    if (isCollapsed) {
      // Collapsing: progress 1 → 0
      // Text fades out in first half (1→0.5), then width shrinks (0.5→0)
      animate(progress, 0, { duration: 0.3, ease: [0.4, 0, 0.2, 1] });
    } else {
      // Expanding: progress 0 → 1
      // Width grows first (0→0.5), then text fades in (0.5→1)
      animate(progress, 1, { duration: 0.3, ease: [0.4, 0, 0.2, 1] });
    }
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
    <motion.aside
      className="flex flex-col flex-shrink-0 bg-secondary/40 border-r border-border/40"
      style={{ width: smoothWidth, overflow: "hidden" }}
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
          />
        ))}
      </nav>

      {/* Footer */}
      <div className="flex flex-col gap-0.5 px-2 pb-1.5">
        {/* Capture toggles */}
        <RewindToggle isCollapsed={isCollapsed} textOpacity={textOpacity} />
        <AudioToggle isCollapsed={isCollapsed} textOpacity={textOpacity} />
        <FocusToggle isCollapsed={isCollapsed} textOpacity={textOpacity} />

        <div className="border-t border-border/30 pt-0.5 mt-0.5">
          <motion.div
            className="overflow-hidden"
            style={{ paddingLeft: ICON_PL, opacity: textOpacity }}
          >
            <span className="text-[11px] text-muted-foreground/60 truncate block whitespace-nowrap leading-tight py-0.5">
              {userEmail}
            </span>
          </motion.div>

          <SidebarRow
            icon={LogOut}
            label="Sign Out"
            isCollapsed={isCollapsed}
            textOpacity={textOpacity}
            onClick={signOut}
          />
        </div>

        <div className="border-t border-border/30 pt-0.5">
          <SidebarRow
            icon={isCollapsed ? ChevronsRight : ChevronsLeft}
            label={isCollapsed ? "Expand (⌘B)" : "Collapse (⌘B)"}
            isCollapsed={isCollapsed}
            textOpacity={textOpacity}
            onClick={toggle}
          />
        </div>
      </div>
    </motion.aside>
  );
}

function NavItem({
  to,
  label,
  icon: Icon,
  isCollapsed,
  textOpacity,
}: {
  to: string;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  isCollapsed: boolean;
  textOpacity: ReturnType<typeof useTransform<number, number>>;
}) {
  const location = useLocation();
  const isActive = to === "/" ? location.pathname === "/" : location.pathname.startsWith(to);

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
        className="whitespace-nowrap text-[13px] font-medium"
        style={{ opacity: textOpacity }}
      >
        {label}
      </motion.span>
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
}

function SidebarRow({
  icon: Icon,
  label,
  isCollapsed,
  textOpacity,
  onClick,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string;
  isCollapsed: boolean;
  textOpacity: ReturnType<typeof useTransform<number, number>>;
  onClick: () => void;
}) {
  const button = (
    <button
      onClick={onClick}
      className="flex items-center gap-3 h-8 rounded-lg transition-colors text-muted-foreground hover:text-foreground hover:bg-accent/50 w-full overflow-hidden"
      style={{ paddingLeft: ICON_PL, paddingRight: ICON_PL }}
    >
      <Icon size={16} className="flex-shrink-0" />
      <motion.span
        className="whitespace-nowrap text-[13px] font-medium"
        style={{ opacity: textOpacity }}
      >
        {label}
      </motion.span>
    </button>
  );

  if (isCollapsed) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>{button}</TooltipTrigger>
        <TooltipContent side="right" sideOffset={8}>
          {label}
        </TooltipContent>
      </Tooltip>
    );
  }

  return button;
}

function SwitchRow({
  icon: Icon,
  label,
  tooltip,
  checked,
  onToggle,
  active,
  elapsed,
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
  isCollapsed: boolean;
  textOpacity: ReturnType<typeof useTransform<number, number>>;
}) {
  const row = (
    <div
      className="flex items-center gap-3 h-9 rounded-lg text-muted-foreground w-full overflow-hidden"
      style={{ paddingLeft: ICON_PL, paddingRight: ICON_PL }}
      title={tooltip}
    >
      <Icon
        size={16}
        className={`flex-shrink-0 ${active ? "text-green-500" : ""}`}
      />
      <motion.div
        className="flex flex-col min-w-0 flex-1"
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
      <motion.div style={{ opacity: textOpacity }}>
        <Switch checked={checked} onCheckedChange={onToggle} aria-label={label} />
      </motion.div>
    </div>
  );

  if (isCollapsed) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            onClick={onToggle}
            className="flex items-center justify-center h-8 w-full rounded-lg transition-colors hover:bg-accent/50"
            aria-label={label}
          >
            <Icon
              size={16}
              className={
                checked
                  ? active
                    ? "text-green-500"
                    : "text-amber-500"
                  : "text-muted-foreground"
              }
            />
          </button>
        </TooltipTrigger>
        <TooltipContent side="right" sideOffset={8}>
          {tooltip}
        </TooltipContent>
      </Tooltip>
    );
  }

  return row;
}

function RewindToggle(props: {
  isCollapsed: boolean;
  textOpacity: ReturnType<typeof useTransform<number, number>>;
}) {
  const { rewindEnabled, isCapturing, inCommercialHours, captureStartedAt, toggleRewind } =
    useRewindStore();
  const elapsed = useElapsed(captureStartedAt);

  const tooltip = !rewindEnabled
    ? "Screen recording off"
    : isCapturing
      ? `Recording screen${elapsed ? ` — ${elapsed}` : ""}`
      : !inCommercialHours
        ? "Paused — only captures Mon-Fri 9am-5pm"
        : "Screen recording on";

  return (
    <SwitchRow
      icon={Monitor}
      label="Rewind"
      tooltip={tooltip}
      checked={rewindEnabled}
      onToggle={toggleRewind}
      active={isCapturing}
      elapsed={elapsed}
      {...props}
    />
  );
}

function AudioToggle(props: {
  isCollapsed: boolean;
  textOpacity: ReturnType<typeof useTransform<number, number>>;
}) {
  const { audioEnabled, isRecording, inCommercialHours, recordingStartedAt, toggleAudio } =
    useAudioStore();
  const elapsed = useElapsed(recordingStartedAt);

  const tooltip = !audioEnabled
    ? "Audio recording off"
    : isRecording
      ? `Recording audio${elapsed ? ` — ${elapsed}` : ""}`
      : !inCommercialHours
        ? "Paused — only captures Mon-Fri 9am-5pm"
        : "Audio recording on";

  return (
    <SwitchRow
      icon={Mic}
      label="Audio"
      tooltip={tooltip}
      checked={audioEnabled}
      onToggle={toggleAudio}
      active={isRecording}
      elapsed={elapsed}
      {...props}
    />
  );
}

function FocusToggle(props: {
  isCollapsed: boolean;
  textOpacity: ReturnType<typeof useTransform<number, number>>;
}) {
  const { focusEnabled, isAnalyzing, monitoringStartedAt, toggleFocus } =
    useFocusStore();
  const elapsed = useElapsed(monitoringStartedAt);

  const tooltip = !focusEnabled
    ? "Focus monitoring off"
    : isAnalyzing
      ? `Analyzing focus${elapsed ? ` — ${elapsed}` : ""}`
      : `Focus monitoring on${elapsed ? ` — ${elapsed}` : ""}`;

  return (
    <SwitchRow
      icon={Eye}
      label="Focus"
      tooltip={tooltip}
      checked={focusEnabled}
      onToggle={toggleFocus}
      active={focusEnabled && isAnalyzing}
      elapsed={elapsed}
      {...props}
    />
  );
}
