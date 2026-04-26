import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentType,
  type ReactNode,
} from "react";
import { AnimatePresence, motion } from "motion/react";
import { invoke } from "@tauri-apps/api/core";
import {
  AlertTriangle,
  AudioLines,
  Bell,
  Bot,
  Brain,
  Check,
  ChevronRight,
  Copy,
  Info,
  Keyboard,
  Laptop,
  Lightbulb,
  ListTodo,
  Loader2,
  LogOut,
  MicIcon,
  Monitor,
  Moon,
  Palette,
  PlayCircle,
  RotateCcw,
  Rewind as RewindIcon,
  Search,
  SendHorizontal,
  Settings as SettingsIcon,
  Sun,
  Target,
  TerminalSquare,
  Trash2,
  UserRound,
} from "lucide-react";
import { useAuthStore } from "../../stores/authStore";
import { useDevStore } from "../../stores/devStore";
import { useOnboardingStore } from "../../stores/onboardingStore";
import { useOnboardingCompanionStore } from "../../stores/onboardingCompanionStore";
import { useThemeStore, type ThemeMode } from "../../stores/themeStore";
import { useSidebarStore } from "../../stores/sidebarStore";
import {
  useCompanionSettingsStore,
  type CompanionPttKey,
} from "../../stores/companionSettingsStore";
import {
  useAudioStore,
  TRANSCRIPTION_LANGUAGES,
} from "../../stores/audioStore";
import type {
  VadMode,
  SystemAudioProbe,
  LiveCaptureProbe,
  ProbeTranscriptEvent,
} from "../../services/audioCapture";
import {
  listDevices,
  probeSystemAudio,
  probeLiveCapture,
  requestSystemAudioPermission,
  type AudioDevice,
} from "../../services/audioCapture";
import { listen } from "@tauri-apps/api/event";
import { useRewindStore } from "../../stores/rewindStore";
import { useFocusStore } from "../../stores/focusStore";
import { useInsightAssistantSettings } from "../../services/insightAssistantSettings";
import { useTaskAssistantSettings } from "../../services/taskAssistantSettings";
import { useMemoryAssistantSettings } from "../../services/memoryAssistantSettings";
import { notify } from "../../services/notifications";
import { runCompanionTestTask } from "../../services/companionAssistant";
import { CompanionSessionsViewer } from "../companion/CompanionSessionsViewer";
import { useShortcutCapture } from "../../hooks/useShortcutCapture";
import { usePttDiagnostics } from "../../hooks/usePttDiagnostics";
import { KeyCapDisplay } from "../onboarding/animations/KeyCapDisplay";
import { Switch } from "../ui/switch";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { ScrollArea } from "../ui/scroll-area";
import { Separator } from "../ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { cn } from "@/lib/utils";
import { PttDebugPanel } from "./PttDebugPanel";

type CategoryId =
  | "general"
  | "account"
  | "appearance"
  | "audio"
  | "rewind"
  | "shortcuts"
  | "notifications"
  | "companion"
  | "developer";

interface CategoryMeta {
  id: CategoryId;
  label: string;
  description: string;
  icon: ComponentType<{ className?: string; size?: number }>;
  iconTone: string;
  keywords: string[];
}

const CATEGORIES: readonly CategoryMeta[] = [
  {
    id: "general",
    label: "General",
    description: "App info, version, platform",
    icon: SettingsIcon,
    iconTone: "from-slate-500 to-slate-700",
    keywords: ["general", "app", "version", "about", "platform"],
  },
  {
    id: "account",
    label: "Account",
    description: "Sign-in, onboarding, identity",
    icon: UserRound,
    iconTone: "from-blue-500 to-indigo-600",
    keywords: ["account", "email", "user", "sign out", "onboarding"],
  },
  {
    id: "appearance",
    label: "Appearance",
    description: "Theme, accent, sidebar",
    icon: Palette,
    iconTone: "from-pink-500 to-rose-600",
    keywords: ["appearance", "theme", "dark", "light", "sidebar"],
  },
  {
    id: "audio",
    label: "Audio",
    description: "Input, language, transcription",
    icon: AudioLines,
    iconTone: "from-cyan-500 to-sky-600",
    keywords: ["audio", "microphone", "speaker", "input", "language", "vad"],
  },
  {
    id: "rewind",
    label: "Rewind",
    description: "Screen recall and history",
    icon: RewindIcon,
    iconTone: "from-amber-500 to-orange-600",
    keywords: ["rewind", "screen", "recall", "history", "capture"],
  },
  {
    id: "shortcuts",
    label: "Shortcuts",
    description: "Keyboard bindings",
    icon: Keyboard,
    iconTone: "from-violet-500 to-purple-600",
    keywords: ["shortcut", "keyboard", "hotkey", "ptt", "bindings"],
  },
  {
    id: "notifications",
    label: "Notifications",
    description: "Alerts, proactive extraction",
    icon: Bell,
    iconTone: "from-emerald-500 to-teal-600",
    keywords: [
      "notifications",
      "alerts",
      "banner",
      "focus",
      "push",
      "proactive",
      "memory",
      "memories",
      "tasks",
      "extraction",
    ],
  },
  {
    id: "companion",
    label: "Companion",
    description: "AI buddy, PTT key, TTS voice",
    icon: Bot,
    iconTone: "from-blue-500 to-cyan-600",
    keywords: ["companion", "ptt", "push-to-talk", "fn", "tts", "voice", "speak", "buddy"],
  },
  {
    id: "developer",
    label: "Developer",
    description: "Diagnostics and experiments",
    icon: TerminalSquare,
    iconTone: "from-zinc-500 to-zinc-700",
    keywords: ["developer", "diagnostics", "debug", "ptt", "memory"],
  },
];

export function SettingsPage() {
  const [active, setActive] = useState<CategoryId>("general");
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return CATEGORIES;
    return CATEGORIES.filter((c) =>
      [c.label, c.description, ...c.keywords].some((k) =>
        k.toLowerCase().includes(q),
      ),
    );
  }, [query]);

  return (
    <div className="flex h-full min-h-0 flex-1 bg-background">
      <aside className="flex w-[260px] shrink-0 flex-col border-r border-border/40 bg-secondary/20">
        <div className="px-5 pt-5 pb-3">
          <h1 className="text-lg font-semibold tracking-tight text-foreground">
            Settings
          </h1>
          <p className="text-xs text-muted-foreground">
            Tailor Nooto to the way you work.
          </p>
        </div>
        <div className="px-3 pb-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search settings"
              className="h-8 pl-8 text-xs"
            />
          </div>
        </div>
        <ScrollArea className="min-h-0 flex-1 px-2 pb-3">
          <nav className="flex flex-col gap-0.5" aria-label="Settings categories">
            {filtered.map((cat) => (
              <CategoryRow
                key={cat.id}
                meta={cat}
                active={cat.id === active}
                onClick={() => setActive(cat.id)}
              />
            ))}
            {filtered.length === 0 && (
              <p className="px-3 pt-6 text-center text-xs text-muted-foreground">
                No matching settings.
              </p>
            )}
          </nav>
        </ScrollArea>
      </aside>

      <section className="flex min-h-0 flex-1 flex-col">
        <AnimatePresence mode="wait">
          <motion.div
            key={active}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.16, ease: "easeOut" }}
            className="flex min-h-0 flex-1 flex-col"
          >
            <DetailPane categoryId={active} />
          </motion.div>
        </AnimatePresence>
      </section>
    </div>
  );
}

function CategoryRow({
  meta,
  active,
  onClick,
}: {
  meta: CategoryMeta;
  active: boolean;
  onClick: () => void;
}) {
  const Icon = meta.icon;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group flex items-center gap-2.5 rounded-md px-2 py-1.5 text-left transition-colors",
        active
          ? "bg-accent text-accent-foreground"
          : "text-foreground/80 hover:bg-accent/60 hover:text-foreground",
      )}
    >
      <span
        className={cn(
          "grid size-7 shrink-0 place-items-center rounded-md bg-gradient-to-br shadow-sm ring-1 ring-white/10",
          meta.iconTone,
        )}
      >
        <Icon className="size-3.5 text-white" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px] font-medium leading-none">
          {meta.label}
        </span>
        <span className="mt-0.5 block truncate text-[11px] leading-none text-muted-foreground">
          {meta.description}
        </span>
      </span>
      <ChevronRight
        className={cn(
          "size-3.5 shrink-0 text-muted-foreground/60 transition-opacity",
          active ? "opacity-100" : "opacity-0 group-hover:opacity-60",
        )}
      />
    </button>
  );
}

function DetailPane({ categoryId }: { categoryId: CategoryId }) {
  const meta = CATEGORIES.find((c) => c.id === categoryId)!;

  return (
    <>
      <header className="flex shrink-0 items-center gap-3 border-b border-border/40 px-6 py-4">
        <span
          className={cn(
            "grid size-9 shrink-0 place-items-center rounded-lg bg-gradient-to-br shadow-sm ring-1 ring-white/10",
            meta.iconTone,
          )}
        >
          <meta.icon className="size-4 text-white" />
        </span>
        <div className="min-w-0">
          <h2 className="text-base font-semibold leading-tight text-foreground">
            {meta.label}
          </h2>
          <p className="text-xs text-muted-foreground">{meta.description}</p>
        </div>
      </header>

      <ScrollArea className="min-h-0 flex-1">
        <div className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-6 py-6">
          {categoryId === "general" && <GeneralPane />}
          {categoryId === "account" && <AccountPane />}
          {categoryId === "appearance" && <AppearancePane />}
          {categoryId === "audio" && <AudioPane />}
          {categoryId === "rewind" && <RewindPane />}
          {categoryId === "shortcuts" && <ShortcutsPane />}
          {categoryId === "notifications" && <NotificationsPane />}
          {categoryId === "companion" && <CompanionPane />}
          {categoryId === "developer" && <DeveloperPane />}
        </div>
      </ScrollArea>
    </>
  );
}

// ---------------------------------------------------------------------------
// Primitives
// ---------------------------------------------------------------------------

function Group({
  title,
  description,
  children,
}: {
  title?: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-2">
      {(title || description) && (
        <div className="px-1">
          {title && (
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              {title}
            </h3>
          )}
          {description && (
            <p className="mt-0.5 text-[11px] text-muted-foreground/80">
              {description}
            </p>
          )}
        </div>
      )}
      <div className="divide-y divide-border/40 overflow-hidden rounded-xl border border-border/40 bg-card/40">
        {children}
      </div>
    </section>
  );
}

function Row({
  label,
  description,
  control,
  children,
}: {
  label: ReactNode;
  description?: ReactNode;
  control?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="flex min-h-[52px] items-center gap-4 px-4 py-3">
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-medium leading-tight text-foreground">
          {label}
        </div>
        {description && (
          <div className="mt-0.5 text-[11.5px] leading-snug text-muted-foreground">
            {description}
          </div>
        )}
        {children && <div className="mt-2">{children}</div>}
      </div>
      {control && <div className="shrink-0">{control}</div>}
    </div>
  );
}

function IconRow({
  icon: Icon,
  tone,
  label,
  description,
  control,
}: {
  icon: ComponentType<{ className?: string }>;
  tone: string;
  label: ReactNode;
  description?: ReactNode;
  control?: ReactNode;
}) {
  return (
    <div className="flex min-h-[56px] items-center gap-3 px-4 py-3">
      <span
        className={cn(
          "grid size-8 shrink-0 place-items-center rounded-lg bg-gradient-to-br shadow-sm ring-1 ring-white/10",
          tone,
        )}
      >
        <Icon className="size-4 text-white" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-medium leading-tight text-foreground">
          {label}
        </div>
        {description && (
          <div className="mt-0.5 text-[11.5px] leading-snug text-muted-foreground">
            {description}
          </div>
        )}
      </div>
      {control && <div className="shrink-0">{control}</div>}
    </div>
  );
}

function CopyableValue({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  if (!value) {
    return <span className="text-xs text-muted-foreground">N/A</span>;
  }
  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      /* clipboard unavailable — silent */
    }
  };
  return (
    <button
      type="button"
      onClick={onCopy}
      className="group/copy inline-flex max-w-[220px] items-center gap-1.5 rounded-md bg-muted/60 px-2 py-1 font-mono text-[11px] text-foreground/80 transition-colors hover:bg-muted"
      title="Copy to clipboard"
    >
      <span className="truncate">{value}</span>
      {copied ? (
        <Check className="size-3 shrink-0 text-emerald-500" />
      ) : (
        <Copy className="size-3 shrink-0 text-muted-foreground opacity-60 group-hover/copy:opacity-100" />
      )}
    </button>
  );
}

function Segmented<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: readonly { value: T; label: string; icon?: ComponentType<{ className?: string }> }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex items-center gap-0.5 rounded-lg border border-border/60 bg-muted/40 p-0.5">
      {options.map((opt) => {
        const Icon = opt.icon;
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[12px] font-medium transition-colors",
              active
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {Icon && <Icon className="size-3.5" />}
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

function Slider({
  value,
  min,
  max,
  step = 1,
  onChange,
  formatValue,
}: {
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (n: number) => void;
  formatValue?: (n: number) => string;
}) {
  return (
    <div className="flex min-w-[180px] items-center gap-2">
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1.5 w-[140px] cursor-pointer appearance-none rounded-full bg-muted accent-primary"
      />
      <span className="min-w-[48px] text-right font-mono text-[11px] text-muted-foreground">
        {formatValue ? formatValue(value) : value}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Panes
// ---------------------------------------------------------------------------

function GeneralPane() {
  return (
    <Group title="About">
      <Row label="App" control={<span className="text-[13px]">Nooto Desktop</span>} />
      <Row label="Version" control={<span className="text-[13px]">0.1.0</span>} />
      <Row
        label="Platform"
        control={<span className="text-[13px]">Tauri 2.0</span>}
      />
      <Row
        label="Build channel"
        description="Switch between stable and beta channels."
        control={
          <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-400">
            Stable
          </span>
        }
      />
    </Group>
  );
}

function AccountPane() {
  const { userEmail, userId, signOut } = useAuthStore();
  const onReplayOnboarding = () => {
    useOnboardingStore.getState().resetOnboarding();
    useOnboardingCompanionStore.getState().reset();
  };

  return (
    <>
      <Group title="Identity">
        <Row
          label="Email"
          control={
            <span className="max-w-[220px] truncate text-[13px] text-foreground/80">
              {userEmail || "Not signed in"}
            </span>
          }
        />
        <Row
          label="User ID"
          description="Used when reporting issues to support."
          control={<CopyableValue value={userId ?? ""} />}
        />
      </Group>

      <Group title="Onboarding">
        <Row
          label="Replay onboarding"
          description="Clear local onboarding state and return to step 1."
          control={
            <Button variant="outline" size="sm" onClick={onReplayOnboarding}>
              <RotateCcw className="size-3.5" />
              Reset
            </Button>
          }
        />
      </Group>

      <Group title="Session">
        <Row
          label="Sign out"
          description="Ends this session on this Mac only."
          control={
            <Button variant="destructive" size="sm" onClick={signOut}>
              <LogOut className="size-3.5" />
              Sign out
            </Button>
          }
        />
      </Group>
    </>
  );
}

// ---------------------------------------------------------------------------
// Appearance
// ---------------------------------------------------------------------------

const THEME_OPTIONS: readonly {
  value: ThemeMode;
  label: string;
  icon: ComponentType<{ className?: string }>;
}[] = [
  { value: "system", label: "System", icon: Monitor },
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
];

function AppearancePane() {
  const mode = useThemeStore((s) => s.mode);
  const setMode = useThemeStore((s) => s.setMode);
  const resolved = useThemeStore((s) => s.resolved);
  const isCollapsed = useSidebarStore((s) => s.isCollapsed);
  const toggleSidebar = useSidebarStore((s) => s.toggle);

  return (
    <>
      <Group title="Theme">
        <Row
          label="Appearance"
          description={`Currently ${resolved}. “System” tracks your macOS preference.`}
          control={
            <Segmented<ThemeMode>
              value={mode}
              options={THEME_OPTIONS}
              onChange={setMode}
            />
          }
        />
        <Row
          label="Accent"
          description="Brand color used across buttons, links, and active states."
          control={
            <span className="inline-flex items-center gap-2">
              <span
                className="size-5 rounded-full ring-2 ring-border/60"
                style={{ background: "var(--color-primary)" }}
              />
              <span className="font-mono text-[11px] text-muted-foreground">
                Nooto Blue
              </span>
            </span>
          }
        />
      </Group>

      <Group title="Layout">
        <Row
          label="Collapse sidebar"
          description="Hide category labels so only icons show. Toggle with ⌘B."
          control={
            <Switch
              checked={isCollapsed}
              onCheckedChange={toggleSidebar}
              aria-label="Collapse sidebar"
            />
          }
        />
      </Group>
    </>
  );
}

// ---------------------------------------------------------------------------
// Audio
// ---------------------------------------------------------------------------

const VAD_OPTIONS: readonly { value: VadMode; label: string; hint: string }[] = [
  { value: "off", label: "Off", hint: "Stream raw mic — best quality" },
  { value: "sensitive", label: "Sensitive", hint: "Catches soft speech" },
  { value: "balanced", label: "Balanced", hint: "Middle ground" },
  { value: "aggressive", label: "Aggressive", hint: "Loud/clear speech only" },
];

function AudioPane() {
  const {
    audioEnabled,
    isRecording,
    deviceName,
    sampleRate,
    inCommercialHours,
    language,
    vadMode,
    selectedInputId,
    liveTranscription,
    toggleAudio,
    setLanguage,
    setVadMode,
    setSelectedInputId,
    setLiveTranscription,
  } = useAudioStore();
  const [devices, setDevices] = useState<AudioDevice[]>([]);
  const [devicesError, setDevicesError] = useState<string | null>(null);

  useEffect(() => {
    listDevices()
      .then((d) => {
        setDevices(d.filter((x) => x.is_input));
        setDevicesError(null);
      })
      .catch((err) => {
        console.warn("[Audio] listDevices failed:", err);
        setDevicesError(err instanceof Error ? err.message : String(err));
      });
  }, []);

  const vadHint =
    VAD_OPTIONS.find((o) => o.value === vadMode)?.hint ?? "";

  return (
    <>
      <Group title="Capture">
        <Row
          label="Record conversations"
          description={
            inCommercialHours
              ? "Nooto captures audio during working hours."
              : "Paused — outside working hours (Mon–Fri 9am–5pm)."
          }
          control={
            <Switch
              checked={audioEnabled}
              onCheckedChange={() => void toggleAudio()}
              aria-label="Audio capture"
            />
          }
        />
        <Row
          label="Live status"
          description={
            isRecording
              ? `Recording from ${deviceName ?? "default device"} at ${sampleRate / 1000}kHz.`
              : "Not currently recording."
          }
          control={
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium",
                isRecording
                  ? "bg-emerald-500/15 text-emerald-400"
                  : "bg-muted text-muted-foreground",
              )}
            >
              <span
                className={cn(
                  "size-1.5 rounded-full",
                  isRecording ? "bg-emerald-500 animate-pulse" : "bg-muted-foreground/60",
                )}
              />
              {isRecording ? "Live" : "Idle"}
            </span>
          }
        />
      </Group>

      <Group title="Input device">
        <Row
          label="Microphone"
          description={
            devicesError
              ? `Couldn't list devices: ${devicesError}`
              : "Changing this restarts the active recording."
          }
          control={
            <Select
              value={selectedInputId ?? "__default__"}
              onValueChange={(v) =>
                void setSelectedInputId(v === "__default__" ? null : v)
              }
            >
              <SelectTrigger size="sm" className="min-w-[200px] text-xs">
                <SelectValue placeholder="System default" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__default__">
                  <MicIcon className="size-3.5" />
                  System default
                </SelectItem>
                {devices.map((d) => (
                  <SelectItem key={d.id} value={d.id}>
                    {d.name}
                    {d.is_default ? " (default)" : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          }
        />
      </Group>

      <Group title="Transcription">
        <Row
          label="Live transcription"
          description="Show captions while recording (uses streaming minutes)."
          control={
            <Switch
              checked={liveTranscription}
              onCheckedChange={(v) => void setLiveTranscription(v)}
              aria-label="Live transcription"
            />
          }
        />
        <Row
          label="Language"
          description="Language used for live transcription."
          control={
            <Select
              value={language}
              onValueChange={(v) => void setLanguage(v)}
            >
              <SelectTrigger size="sm" className="min-w-[200px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TRANSCRIPTION_LANGUAGES.map((l) => (
                  <SelectItem key={l.code} value={l.code}>
                    {l.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          }
        />
        <Row
          label="Voice activity detection"
          description={vadHint}
          control={
            <Select
              value={vadMode}
              onValueChange={(v) => void setVadMode(v as VadMode)}
            >
              <SelectTrigger size="sm" className="min-w-[160px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {VAD_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          }
        />
      </Group>

      <Group title="System audio">
        <PermissionRequestRow />
        <ActiveCaptureRow />
        <SystemAudioDebugRow />
        <LiveCaptureDebugRow />
      </Group>
    </>
  );
}

function PermissionRequestRow() {
  const [status, setStatus] = useState<"idle" | "running" | "granted" | "denied">(
    "idle",
  );
  const [message, setMessage] = useState<string | null>(null);

  const run = async () => {
    setStatus("running");
    setMessage(null);
    try {
      const probe = await requestSystemAudioPermission();
      if (probe.ok) {
        setStatus("granted");
        setMessage(probe.message);
      } else {
        setStatus("denied");
        setMessage(probe.message);
      }
    } catch (err) {
      setStatus("denied");
      setMessage(err instanceof Error ? err.message : String(err));
    }
  };

  const description = (() => {
    if (status === "idle") {
      return "Opens System Settings → Privacy & Security → Screen & System Audio Recording and triggers the TCC prompt. Enable Nooto there (and remove any stale duplicate entries with the − button).";
    }
    if (status === "running") {
      return "Opening System Settings and probing the tap…";
    }
    if (status === "granted") {
      return `Granted — ${message ?? ""}`;
    }
    return `Not granted — ${message ?? "tap returned no samples"}. Toggle Nooto on in System Settings, then click Test below.`;
  })();

  const icon = (() => {
    if (status === "running") {
      return <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" />;
    }
    if (status === "granted") {
      return <Check className="size-4 shrink-0 text-emerald-500" />;
    }
    if (status === "denied") {
      return <AlertTriangle className="size-4 shrink-0 text-amber-500" />;
    }
    return <Info className="size-4 shrink-0 text-muted-foreground/70" />;
  })();

  return (
    <Row
      label={
        <span className="inline-flex items-center gap-2">
          {icon}
          Grant system audio permission
        </span>
      }
      description={description}
      control={
        <Button
          size="sm"
          variant="outline"
          onClick={() => void run()}
          disabled={status === "running"}
        >
          {status === "running" ? "Opening…" : "Open settings & request"}
        </Button>
      }
    />
  );
}

/// During an active recording, polls the plugin every 500 ms and shows
/// live per-channel sample counters. If `sys=0` while the user is playing
/// something, the tap isn't delivering frames during a real meeting even
/// if the one-shot probe succeeded — the smoking gun we need.
function ActiveCaptureRow() {
  const {
    isRecording,
    systemAudioActive,
    micSamplesTotal,
    sysSamplesTotal,
    refreshState,
  } = useAudioStore();

  useEffect(() => {
    if (!isRecording) return;
    const id = setInterval(() => {
      void refreshState();
    }, 500);
    return () => clearInterval(id);
  }, [isRecording, refreshState]);

  const description = isRecording
    ? `sys tap ${systemAudioActive ? "active" : "inactive"} — mic ${micSamplesTotal.toLocaleString()} samples · sys ${sysSamplesTotal.toLocaleString()} samples`
    : "Starts updating once you click Start a meeting.";

  const icon = (() => {
    if (!isRecording) {
      return <Info className="size-4 shrink-0 text-muted-foreground/70" />;
    }
    if (!systemAudioActive) {
      return <AlertTriangle className="size-4 shrink-0 text-red-500" />;
    }
    if (sysSamplesTotal === 0) {
      return <Info className="size-4 shrink-0 text-amber-500" />;
    }
    return <Check className="size-4 shrink-0 text-emerald-500" />;
  })();

  return (
    <Row
      label={
        <span className="inline-flex items-center gap-2">
          {icon}
          Active recording
        </span>
      }
      description={description}
    />
  );
}

type SystemAudioProbeStatus =
  | { state: "idle" }
  | { state: "running" }
  | { state: "done"; probe: SystemAudioProbe };

function SystemAudioDebugRow() {
  const [status, setStatus] = useState<SystemAudioProbeStatus>({ state: "idle" });

  const runProbe = async () => {
    setStatus({ state: "running" });
    try {
      const probe = await probeSystemAudio();
      setStatus({ state: "done", probe });
    } catch (err) {
      setStatus({
        state: "done",
        probe: {
          ok: false,
          platform: "unknown",
          message: err instanceof Error ? err.message : String(err),
          samples_received: 0,
        },
      });
    }
  };

  const description = (() => {
    if (status.state === "idle") {
      return "Run a 600 ms Core Audio tap probe to verify TCC permission and whether frames are being delivered. Have something playing through the speakers for the most useful result.";
    }
    if (status.state === "running") {
      return "Probing Core Audio tap…";
    }
    const { probe } = status;
    return `${probe.platform} — ${probe.message}`;
  })();

  const icon = (() => {
    if (status.state === "running") {
      return <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" />;
    }
    if (status.state === "done") {
      if (status.probe.ok && status.probe.samples_received > 0) {
        return <Check className="size-4 shrink-0 text-emerald-500" />;
      }
      if (status.probe.ok) {
        return <Info className="size-4 shrink-0 text-amber-500" />;
      }
      return <AlertTriangle className="size-4 shrink-0 text-red-500" />;
    }
    return <Info className="size-4 shrink-0 text-muted-foreground/70" />;
  })();

  return (
    <Row
      label={
        <span className="inline-flex items-center gap-2">
          {icon}
          Capture system audio (YouTube, calls, etc.)
        </span>
      }
      description={description}
      control={
        <Button
          size="sm"
          variant="outline"
          onClick={() => void runProbe()}
          disabled={status.state === "running"}
        >
          {status.state === "running" ? "Probing…" : "Test"}
        </Button>
      }
    />
  );
}

type LiveProbeStatus =
  | { state: "idle" }
  | { state: "running"; endsAt: number }
  | { state: "done"; probe: LiveCaptureProbe };

const LIVE_PROBE_MS = 10_000;

function LiveCaptureDebugRow() {
  const [status, setStatus] = useState<LiveProbeStatus>({ state: "idle" });
  const [countdown, setCountdown] = useState(0);
  const [transcripts, setTranscripts] = useState<ProbeTranscriptEvent[]>([]);

  useEffect(() => {
    if (status.state !== "running") return;
    const tick = () => {
      const remaining = Math.max(0, status.endsAt - Date.now());
      setCountdown(Math.ceil(remaining / 1000));
    };
    tick();
    const id = setInterval(tick, 250);
    return () => clearInterval(id);
  }, [status]);

  useEffect(() => {
    if (status.state !== "running") return;
    let unlisten: (() => void) | null = null;
    void listen<ProbeTranscriptEvent>("probe:transcript", (event) => {
      setTranscripts((prev) => [...prev.slice(-49), event.payload]);
    }).then((fn) => {
      unlisten = fn;
    });
    return () => {
      if (unlisten) unlisten();
    };
  }, [status.state]);

  const runProbe = async () => {
    setTranscripts([]);
    setStatus({ state: "running", endsAt: Date.now() + LIVE_PROBE_MS });
    try {
      const probe = await probeLiveCapture(LIVE_PROBE_MS);
      setStatus({ state: "done", probe });
    } catch (err) {
      setStatus({
        state: "done",
        probe: {
          ok: false,
          duration_ms: 0,
          mic_samples: 0,
          sys_samples: 0,
          mic_level: 0,
          sys_level: 0,
          mic_peak_i16: 0,
          sys_peak_i16: 0,
          mic_nonzero: 0,
          sys_nonzero: 0,
          transcription_connected: false,
          transcript_count: 0,
          message: err instanceof Error ? err.message : String(err),
        },
      });
    }
  };

  const description = (() => {
    if (status.state === "idle") {
      return `Captures mic + system audio for ${LIVE_PROBE_MS / 1000}s, runs it through Deepgram, and shows live transcript bubbles below (mic = right, system = left). Start a YouTube video, then click Test.`;
    }
    if (status.state === "running") {
      return `Capturing… ${countdown}s left. Talk and let audio play.`;
    }
    const p = status.probe;
    const wsTag = p.transcription_connected
      ? `${p.transcript_count} transcripts`
      : "no transcription (no auth or WS failed)";
    return `${p.message} — mic ${p.mic_samples} samples (RMS ${p.mic_level.toFixed(3)}) · sys ${p.sys_samples} samples (RMS ${p.sys_level.toFixed(3)}) · ${wsTag}`;
  })();

  const icon = (() => {
    if (status.state === "running") {
      return <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" />;
    }
    if (status.state === "done") {
      if (status.probe.ok && status.probe.sys_samples > 0) {
        return <Check className="size-4 shrink-0 text-emerald-500" />;
      }
      if (status.probe.mic_samples > 0) {
        return <Info className="size-4 shrink-0 text-amber-500" />;
      }
      return <AlertTriangle className="size-4 shrink-0 text-red-500" />;
    }
    return <Info className="size-4 shrink-0 text-muted-foreground/70" />;
  })();

  const showBubbles = status.state !== "idle" && transcripts.length > 0;

  return (
    <Row
      label={
        <span className="inline-flex items-center gap-2">
          {icon}
          Live capture test (mic + system + Deepgram)
        </span>
      }
      description={description}
      control={
        <Button
          size="sm"
          variant="outline"
          onClick={() => void runProbe()}
          disabled={status.state === "running"}
        >
          {status.state === "running" ? `${countdown}s…` : "Test"}
        </Button>
      }
    >
      {showBubbles && (
        <div className="mt-2 max-h-48 space-y-1 overflow-y-auto rounded-lg border border-border/40 bg-muted/30 p-2 text-[11.5px]">
          {transcripts.map((t, i) => (
            <div
              key={i}
              className={cn(
                "flex gap-2",
                t.is_user ? "justify-end" : "justify-start",
              )}
            >
              <div
                className={cn(
                  "max-w-[85%] rounded-md px-2 py-1 leading-snug",
                  t.is_user
                    ? "bg-primary/15 text-foreground"
                    : "bg-emerald-500/15 text-foreground",
                  !t.is_final && "opacity-60 italic",
                )}
              >
                <span className="mr-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  {t.is_user ? "mic" : "sys"}
                </span>
                {t.text}
              </div>
            </div>
          ))}
        </div>
      )}
    </Row>
  );
}

// ---------------------------------------------------------------------------
// Rewind
// ---------------------------------------------------------------------------

const MAX_WIDTH_OPTIONS = [1280, 1920, 2560, 3000] as const;
const DEFAULT_INTERVAL_MS = 3000;
const DEFAULT_QUALITY = 80;
const DEFAULT_MAX_WIDTH = 3000;

function describeRewindState(
  enabled: boolean,
  capturing: boolean,
  inHours: boolean,
): string {
  if (!enabled) return "Off. Your screen is not being captured.";
  if (capturing) return "Capturing your screen while you work.";
  if (inHours) return "Enabled, waiting to start.";
  return "Paused — outside working hours.";
}

function RewindPane() {
  const rewindEnabled = useRewindStore((s) => s.rewindEnabled);
  const isCapturing = useRewindStore((s) => s.isCapturing);
  const inCommercialHours = useRewindStore((s) => s.inCommercialHours);
  const captureConfig = useRewindStore((s) => s.captureConfig);
  const screenshotsCount = useRewindStore((s) => s.screenshots.length);
  const toggleRewind = useRewindStore((s) => s.toggleRewind);
  const updateConfig = useRewindStore((s) => s.updateConfig);
  const clearAllScreenshots = useRewindStore((s) => s.clearAllScreenshots);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [clearing, setClearing] = useState(false);

  const onClear = async () => {
    setClearing(true);
    try {
      await clearAllScreenshots();
    } finally {
      setClearing(false);
      setConfirmOpen(false);
    }
  };

  return (
    <>
      <Group title="Capture">
        <Row
          label="Screen rewind"
          description={describeRewindState(
            rewindEnabled,
            isCapturing,
            inCommercialHours,
          )}
          control={
            <Switch
              checked={rewindEnabled}
              onCheckedChange={() => void toggleRewind()}
              aria-label="Rewind enabled"
            />
          }
        />
      </Group>

      <Group
        title="Quality"
        description="Balance disk usage against the detail Nooto can recall."
      >
        <Row
          label="Capture interval"
          description="How often a screenshot is taken."
          control={
            <Slider
              value={captureConfig.interval_ms ?? DEFAULT_INTERVAL_MS}
              min={1000}
              max={30000}
              step={500}
              onChange={(v) => updateConfig({ interval_ms: v })}
              formatValue={(v) => `${(v / 1000).toFixed(1)}s`}
            />
          }
        />
        <Row
          label="Image quality"
          description="Higher quality captures more text but uses more disk."
          control={
            <Slider
              value={captureConfig.quality ?? DEFAULT_QUALITY}
              min={40}
              max={95}
              onChange={(v) => updateConfig({ quality: v })}
              formatValue={(v) => `${v}%`}
            />
          }
        />
        <Row
          label="Max width"
          description="Screenshots are downscaled to this width before storing."
          control={
            <Select
              value={String(captureConfig.max_width ?? DEFAULT_MAX_WIDTH)}
              onValueChange={(v) => updateConfig({ max_width: Number(v) })}
            >
              <SelectTrigger size="sm" className="min-w-[120px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MAX_WIDTH_OPTIONS.map((w) => (
                  <SelectItem key={w} value={String(w)}>
                    {w}px
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          }
        />
      </Group>

      <Group title="Storage">
        <Row
          label="Stored screenshots"
          description={
            screenshotsCount === 0
              ? "Nothing captured yet."
              : `Nooto has ${screenshotsCount} screenshot${screenshotsCount === 1 ? "" : "s"} on disk.`
          }
          control={
            <Button
              variant="destructive"
              size="sm"
              onClick={() => setConfirmOpen(true)}
              disabled={screenshotsCount === 0 || clearing}
            >
              <Trash2 className="size-3.5" />
              Clear all
            </Button>
          }
        />
      </Group>

      <div className="flex items-center gap-3 rounded-xl border border-border/40 bg-card/40 px-4 py-3 text-[11.5px] text-muted-foreground">
        <Info className="size-4 shrink-0 text-muted-foreground/70" />
        <span>
          Per-app exclusion lists and privacy filters need new Rust endpoints —
          coming soon.
        </span>
      </div>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete all rewind history?</DialogTitle>
            <DialogDescription>
              This permanently removes all {screenshotsCount} stored screenshot
              {screenshotsCount === 1 ? "" : "s"} and their OCR text. This
              can't be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter showCloseButton={false}>
            <Button
              variant="outline"
              onClick={() => setConfirmOpen(false)}
              disabled={clearing}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => void onClear()}
              disabled={clearing}
            >
              <Trash2 className="size-3.5" />
              {clearing ? "Deleting…" : "Delete everything"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

// ---------------------------------------------------------------------------
// Shortcuts
// ---------------------------------------------------------------------------

type ShortcutKind = "voice" | "floating_bar";

interface ShortcutCaptureState {
  kind: ShortcutKind;
  allowModifierOnly: boolean;
}

function ShortcutsPane() {
  const voiceShortcut = useOnboardingStore((s) => s.voiceShortcut);
  const floatingBarShortcut = useOnboardingStore((s) => s.floatingBarShortcut);
  const setVoiceShortcut = useOnboardingStore((s) => s.setVoiceShortcut);
  const setFloatingBarShortcut = useOnboardingStore(
    (s) => s.setFloatingBarShortcut,
  );
  const [capturing, setCapturing] = useState<ShortcutCaptureState | null>(null);

  const onCommit = async (chord: string) => {
    if (!capturing) return;
    if (capturing.kind === "voice") {
      setVoiceShortcut(chord);
      const ptKey = chord.split("+").pop()?.trim();
      if (ptKey) {
        try {
          await invoke("set_ptt_key", { label: ptKey });
        } catch (err) {
          console.warn("[Shortcuts] set_ptt_key failed:", err);
        }
      }
    } else {
      setFloatingBarShortcut(chord);
    }
    setCapturing(null);
  };

  const onRestoreDefaults = async () => {
    setVoiceShortcut("Option");
    setFloatingBarShortcut("Cmd+\\");
    try {
      await invoke("set_ptt_key", { label: "Option" });
    } catch (err) {
      console.warn("[Shortcuts] set_ptt_key failed:", err);
    }
  };

  return (
    <>
      <Group title="Voice">
        <Row
          label="Push-to-talk key"
          description="Hold to dictate. A single modifier like Option works best."
          control={
            <ShortcutButton
              chord={voiceShortcut}
              onChange={() =>
                setCapturing({ kind: "voice", allowModifierOnly: true })
              }
            />
          }
        />
      </Group>

      <Group title="Floating bar">
        <Row
          label="Toggle shortcut"
          description={
            <>
              Shows or hides the floating composer.{" "}
              <span className="text-amber-400/90">
                Changes take effect after restarting Nooto.
              </span>
            </>
          }
          control={
            <ShortcutButton
              chord={floatingBarShortcut}
              onChange={() =>
                setCapturing({
                  kind: "floating_bar",
                  allowModifierOnly: false,
                })
              }
            />
          }
        />
      </Group>

      <Group title="Reset">
        <Row
          label="Restore defaults"
          description="Push-to-talk back to Option, floating bar back to ⌘\\."
          control={
            <Button
              variant="outline"
              size="sm"
              onClick={() => void onRestoreDefaults()}
            >
              <RotateCcw className="size-3.5" />
              Restore
            </Button>
          }
        />
      </Group>

      <PttListenerStatus />

      <Dialog
        open={capturing !== null}
        onOpenChange={(open) => !open && setCapturing(null)}
      >
        <DialogContent showCloseButton={false}>
          {capturing && (
            <ShortcutCaptureDialog
              kind={capturing.kind}
              allowModifierOnly={capturing.allowModifierOnly}
              onCommit={(chord) => void onCommit(chord)}
              onCancel={() => setCapturing(null)}
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

function ShortcutButton({
  chord,
  onChange,
}: {
  chord: string;
  onChange: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onChange}
      className="group inline-flex items-center gap-2 rounded-md border border-border/60 bg-muted/40 px-2.5 py-1 text-[12px] font-mono text-foreground transition-colors hover:bg-muted"
    >
      <span>{chord || "Not set"}</span>
      <span className="text-[10px] font-sans text-muted-foreground group-hover:text-foreground">
        Change
      </span>
    </button>
  );
}

function ShortcutCaptureDialog({
  kind,
  allowModifierOnly,
  onCommit,
  onCancel,
}: {
  kind: ShortcutKind;
  allowModifierOnly: boolean;
  onCommit: (chord: string) => void;
  onCancel: () => void;
}) {
  const { held, captured, reset } = useShortcutCapture({
    allowModifierOnly,
    disabled: false,
  });

  useEffect(() => {
    // Suspend the static Cmd+\ registration while the user picks, so they
    // can reuse the key without triggering the floating bar.
    invoke("suspend_global_shortcuts").catch(() => {});
    return () => {
      invoke("restore_global_shortcuts").catch(() => {});
    };
  }, []);

  const liveKeys = held.length > 0 ? held : (captured ?? []);

  return (
    <>
      <DialogHeader>
        <DialogTitle>
          {kind === "voice" ? "Pick a push-to-talk key" : "Pick a shortcut"}
        </DialogTitle>
        <DialogDescription>
          {kind === "voice"
            ? "Hold any key or modifier — release to commit. A single modifier like Option works great."
            : "Press the combination you want."}
        </DialogDescription>
      </DialogHeader>

      <div className="flex flex-col items-center gap-3 py-4">
        <KeyCapDisplay keys={liveKeys} active />
        <div className="text-[12px] text-muted-foreground">
          {held.length > 0
            ? "Holding…"
            : captured
              ? "Looks good?"
              : "Waiting for input…"}
        </div>
      </div>

      <DialogFooter showCloseButton={false}>
        <Button variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button variant="outline" onClick={() => reset()} disabled={!captured}>
          Retry
        </Button>
        <Button
          onClick={() => captured && onCommit(captured.join("+"))}
          disabled={!captured}
        >
          Use this shortcut
        </Button>
      </DialogFooter>
    </>
  );
}

function PttListenerStatus() {
  const diag = usePttDiagnostics();

  const status: "unknown" | "ok" | "failed" = diag
    ? diag.listener_failed
      ? "failed"
      : diag.listener_thread_started
        ? "ok"
        : "unknown"
    : "unknown";

  const tone =
    status === "ok"
      ? "bg-emerald-500"
      : status === "failed"
        ? "bg-destructive"
        : "bg-muted-foreground";

  const title =
    status === "ok"
      ? "Listener running"
      : status === "failed"
        ? "Listener failed"
        : "Listener status unknown";

  const detail = diag?.last_key
    ? `Last key: ${diag.last_key}`
    : status === "failed"
      ? diag?.listener_error ??
        "Check Accessibility permissions in System Settings."
      : "Press your push-to-talk key to verify.";

  return (
    <div className="flex items-center gap-3 rounded-xl border border-border/40 bg-card/40 px-4 py-3 text-[12px]">
      <span className={cn("size-2 rounded-full", tone)} />
      <div className="min-w-0 flex-1">
        <div className="text-[12.5px] font-medium text-foreground">{title}</div>
        <div className="text-[11px] text-muted-foreground">{detail}</div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

function NotificationsPane() {
  const focusEnabled = useFocusStore((s) => s.notificationsEnabled);
  const toggleFocus = useFocusStore((s) => s.toggleNotifications);

  const insightsEnabled = useInsightAssistantSettings(
    (s) => s.notificationsEnabled,
  );
  const setInsightsEnabled = useInsightAssistantSettings(
    (s) => s.setNotificationsEnabled,
  );

  const tasksEnabled = useTaskAssistantSettings((s) => s.notificationsEnabled);
  const setTasksEnabled = useTaskAssistantSettings(
    (s) => s.setNotificationsEnabled,
  );

  const memoriesEnabled = useMemoryAssistantSettings(
    (s) => s.notificationsEnabled,
  );
  const setMemoriesEnabled = useMemoryAssistantSettings(
    (s) => s.setNotificationsEnabled,
  );

  // Master toggles for the proactive extraction pipelines. When off, the
  // assistant's frame listener is torn down entirely (no Gemini calls, no
  // screenshot analysis, no notifications) — matches the Swift app.
  const memoryExtractionEnabled = useMemoryAssistantSettings((s) => s.enabled);
  const setMemoryExtractionEnabled = useMemoryAssistantSettings(
    (s) => s.setEnabled,
  );
  const taskExtractionEnabled = useTaskAssistantSettings((s) => s.enabled);
  const setTaskExtractionEnabled = useTaskAssistantSettings(
    (s) => s.setEnabled,
  );

  const [testing, setTesting] = useState(false);
  const resetTimerRef = useRef<number | null>(null);
  useEffect(() => {
    return () => {
      if (resetTimerRef.current !== null) {
        window.clearTimeout(resetTimerRef.current);
      }
    };
  }, []);
  const onTest = async () => {
    setTesting(true);
    try {
      await notify("Nooto", "This is how your notifications will look.");
    } finally {
      resetTimerRef.current = window.setTimeout(() => setTesting(false), 800);
    }
  };

  return (
    <>
      <Group
        title="Proactive extraction"
        description="Turn off to stop Nooto from analyzing screenshots in the background."
      >
        <IconRow
          icon={ListTodo}
          tone="from-indigo-500 to-blue-600"
          label="Proactive tasks"
          description="Extract to-dos from what's on your screen as context changes."
          control={
            <Switch
              checked={taskExtractionEnabled}
              onCheckedChange={setTaskExtractionEnabled}
              aria-label="Proactive task extraction"
            />
          }
        />
        <IconRow
          icon={Brain}
          tone="from-fuchsia-500 to-purple-600"
          label="Proactive memories"
          description="Capture long-term facts and insights from what you read."
          control={
            <Switch
              checked={memoryExtractionEnabled}
              onCheckedChange={setMemoryExtractionEnabled}
              aria-label="Proactive memory extraction"
            />
          }
        />
      </Group>

      <Group
        title="Notifications"
        description="Banner alerts. The extraction pipelines above must be on for task and memory alerts to fire."
      >
        <IconRow
          icon={Target}
          tone="from-rose-500 to-red-600"
          label="Focus alerts"
          description="Nudges when you drift into a distracting app or site."
          control={
            <Switch
              checked={focusEnabled}
              onCheckedChange={toggleFocus}
              aria-label="Focus alerts"
            />
          }
        />
        <IconRow
          icon={Lightbulb}
          tone="from-amber-500 to-yellow-600"
          label="Insights"
          description="Rare, high-signal tips spotted on your screen."
          control={
            <Switch
              checked={insightsEnabled}
              onCheckedChange={setInsightsEnabled}
              aria-label="Insight notifications"
            />
          }
        />
        <IconRow
          icon={ListTodo}
          tone="from-indigo-500 to-blue-600"
          label="Tasks"
          description={
            taskExtractionEnabled
              ? "Tell me when a new task is extracted from a conversation."
              : "Turn on proactive tasks above to receive these."
          }
          control={
            <Switch
              checked={tasksEnabled && taskExtractionEnabled}
              onCheckedChange={setTasksEnabled}
              disabled={!taskExtractionEnabled}
              aria-label="Task notifications"
            />
          }
        />
        <IconRow
          icon={Brain}
          tone="from-fuchsia-500 to-purple-600"
          label="Memories"
          description={
            memoryExtractionEnabled
              ? "Ping me when a new long-term memory is captured."
              : "Turn on proactive memories above to receive these."
          }
          control={
            <Switch
              checked={memoriesEnabled && memoryExtractionEnabled}
              onCheckedChange={setMemoriesEnabled}
              disabled={!memoryExtractionEnabled}
              aria-label="Memory notifications"
            />
          }
        />
      </Group>

      <Group title="Preview">
        <IconRow
          icon={Laptop}
          tone="from-slate-500 to-slate-700"
          label="Send test notification"
          description="Verify that OS banners are getting through."
          control={
            <Button size="sm" onClick={() => void onTest()} disabled={testing}>
              <SendHorizontal className="size-3.5" />
              {testing ? "Sent" : "Send"}
            </Button>
          }
        />
      </Group>

      <div className="flex items-center gap-3 rounded-xl border border-border/40 bg-card/40 px-4 py-3 text-[11.5px] text-muted-foreground">
        <Info className="size-4 shrink-0 text-muted-foreground/70" />
        <span>
          Quiet hours, banner style, and notification sounds aren't wired up
          yet — the Rust notifier currently takes title + body only.
        </span>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Developer
// ---------------------------------------------------------------------------

function DeveloperPane() {
  const {
    developerMode,
    memoryIndicatorEnabled,
    bypassCommercialHours,
    liveTranscriptWindowEnabled,
    toggleDeveloperMode,
    toggleMemoryIndicator,
    toggleBypassCommercialHours,
    toggleLiveTranscriptWindow,
  } = useDevStore();

  return (
    <>
      <Group title="Developer mode">
        <Row
          label="Enable developer mode"
          description="Expose experimental diagnostics, tools, and overlays."
          control={
            <Switch
              checked={developerMode}
              onCheckedChange={toggleDeveloperMode}
              aria-label="Developer mode"
            />
          }
        />
      </Group>

      {developerMode ? (
        <>
          <Group title="Diagnostics">
            <Row
              label="Memory usage indicator"
              description="Show a floating badge with current process / system memory."
              control={
                <Switch
                  checked={memoryIndicatorEnabled}
                  onCheckedChange={toggleMemoryIndicator}
                  aria-label="Memory usage indicator"
                />
              }
            />
            <Row
              label="Bypass working hours"
              description="Allow Rewind and audio capture to run outside Mon–Fri 9am–5pm."
              control={
                <Switch
                  checked={bypassCommercialHours}
                  onCheckedChange={toggleBypassCommercialHours}
                  aria-label="Bypass working hours"
                />
              }
            />
            <Row
              label="Live transcript window"
              description="Show the floating live-transcript overlay during meetings."
              control={
                <Switch
                  checked={liveTranscriptWindowEnabled}
                  onCheckedChange={toggleLiveTranscriptWindow}
                  aria-label="Live transcript window"
                />
              }
            />
          </Group>

          <Group title="Push-to-talk debug">
            <div className="px-4 py-3">
              <PttDebugPanel />
            </div>
          </Group>
        </>
      ) : (
        <div className="flex items-center gap-3 rounded-xl border border-border/40 bg-card/40 px-4 py-4 text-[12.5px] text-muted-foreground">
          <Info className="size-4 shrink-0 text-muted-foreground/70" />
          <span>Turn on developer mode to reveal diagnostics and the PTT debug panel.</span>
        </div>
      )}

      <Separator className="opacity-40" />
    </>
  );
}

// ---------------------------------------------------------------------------
// Companion
// ---------------------------------------------------------------------------

const PTT_KEY_OPTIONS: readonly { value: CompanionPttKey; label: string }[] = [
  { value: "Right Shift", label: "Right Shift" },
  { value: "Cmd+Shift", label: "Cmd + Shift (recommended)" },
  { value: "Cmd+Right Shift", label: "Cmd + Right Shift" },
  { value: "Fn", label: "Fn (Function key — flaky on some keyboards)" },
  { value: "AltGr", label: "AltGr / Right Option (conflicts with Whispr)" },
];

function CompanionPane() {
  const companionEnabled = useCompanionSettingsStore((s) => s.companionEnabled);
  const pttKey = useCompanionSettingsStore((s) => s.pttKey);
  const ttsVoiceId = useCompanionSettingsStore((s) => s.ttsVoiceId);
  const persistPointer = useCompanionSettingsStore((s) => s.persistPointer);
  const setCompanionEnabled = useCompanionSettingsStore((s) => s.setCompanionEnabled);
  const setPttKey = useCompanionSettingsStore((s) => s.setPttKey);
  const setTtsVoiceId = useCompanionSettingsStore((s) => s.setTtsVoiceId);
  const setPersistPointer = useCompanionSettingsStore((s) => s.setPersistPointer);

  const [voices, setVoices] = useState<Array<{ id: string; name: string }>>([]);
  const [testingVoice, setTestingVoice] = useState(false);
  const [runningTestTask, setRunningTestTask] = useState(false);
  const testTimerRef = useRef<number | null>(null);
  /** Error from set_companion_key (key conflict or unsupported key). */
  const [pttKeyError, setPttKeyError] = useState<string | null>(null);
  /** The Whispr PTT key currently configured in Rust — shown as a hint. */
  const [whisprPttKey, setWhisprPttKey] = useState<string | null>(null);

  useEffect(() => {
    invoke<Array<{ identifier: string; name: string }>>("plugin:tts|tts_list_voices")
      .then((list) => {
        const mapped = list.map((v) => ({ id: v.identifier, name: v.name }));
        setVoices(mapped);
        // If no voice is persisted yet, default to the first entry.
        if (!ttsVoiceId && mapped.length > 0) {
          setTtsVoiceId(mapped[0].id);
        }
      })
      .catch((e) => {
        console.warn("[CompanionPane] tts_list_voices failed:", e);
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch the Whispr PTT key so we can warn the user if they try to reuse it.
  useEffect(() => {
    invoke<string>("get_ptt_key")
      .then((key) => setWhisprPttKey(key))
      .catch(() => {
        // Command not present in this build — safe to ignore.
      });
  }, []);

  useEffect(() => {
    return () => {
      if (testTimerRef.current !== null) {
        window.clearTimeout(testTimerRef.current);
      }
    };
  }, []);

  const onPttKeyChange = async (key: CompanionPttKey) => {
    const prev = pttKey;
    setPttKey(key);
    setPttKeyError(null);
    try {
      await invoke("set_companion_key", { label: key });
    } catch (e) {
      // Rust rejected the change (conflict or unsupported key) — revert the
      // local store to the previous value so it stays in sync with Rust.
      setPttKey(prev);
      const errMsg = e instanceof Error ? e.message : String(e);
      setPttKeyError(errMsg);
      console.warn("[CompanionPane] set_companion_key failed:", e);
    }
  };

  const onTestVoice = async () => {
    setTestingVoice(true);
    try {
      await invoke("plugin:tts|tts_speak", {
        text: "This is how your companion will sound.",
        ...(ttsVoiceId ? { voice: ttsVoiceId } : {}),
      });
    } catch (e) {
      console.warn("[CompanionPane] tts_speak failed:", e);
    } finally {
      testTimerRef.current = window.setTimeout(() => setTestingVoice(false), 3000);
    }
  };

  const onRunTestTask = async () => {
    setRunningTestTask(true);
    try {
      await runCompanionTestTask();
    } catch (e) {
      console.warn("[CompanionPane] runCompanionTestTask failed:", e);
    } finally {
      // Re-enable the button after the typical pipeline duration. The actual
      // buddy + TTS continue independently; this just debounces rapid clicks.
      window.setTimeout(() => setRunningTestTask(false), 4000);
    }
  };

  const selectedVoiceName =
    voices.find((v) => v.id === ttsVoiceId)?.name ?? (ttsVoiceId ? ttsVoiceId : "System default");

  // Build the description for the PTT key row — include a Whispr conflict hint
  // when the Whispr key is known.
  const pttKeyDescription = whisprPttKey
    ? `Hold to invoke the AI pipeline. Whispr uses ${whisprPttKey} — pick a different key here.`
    : "Hold this key to invoke the voice-to-screen AI pipeline.";

  return (
    <>
      <Group title="General">
        <Row
          label="Enable Companion"
          description="When off, the Fn PTT key is still captured but the AI pipeline does not run."
          control={
            <Switch
              checked={companionEnabled}
              onCheckedChange={setCompanionEnabled}
              aria-label="Enable Companion"
            />
          }
        />
        <Row
          label="Keep pointer until clicked"
          description="When on, the blue ring stays on screen after an answer until you click anywhere to dismiss. When off, it fades after a couple of seconds."
          control={
            <Switch
              checked={persistPointer}
              onCheckedChange={setPersistPointer}
              aria-label="Keep pointer until clicked"
            />
          }
        />
      </Group>

      <Group title="Push-to-talk">
        <Row
          label="Companion PTT key"
          description={pttKeyDescription}
          control={
            <Select
              value={pttKey}
              onValueChange={(v) => void onPttKeyChange(v as CompanionPttKey)}
            >
              <SelectTrigger size="sm" className="min-w-[200px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PTT_KEY_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          }
        >
          {pttKeyError && (
            <p className="text-destructive text-[11.5px]">{pttKeyError}</p>
          )}
        </Row>
      </Group>

      <Group title="Voice">
        <Row
          label="TTS voice"
          description="The system voice used to speak Companion answers aloud."
          control={
            voices.length > 0 ? (
              <Select
                value={ttsVoiceId}
                onValueChange={setTtsVoiceId}
              >
                <SelectTrigger size="sm" className="min-w-[200px] text-xs">
                  <SelectValue placeholder={selectedVoiceName} />
                </SelectTrigger>
                <SelectContent>
                  {voices.map((v) => (
                    <SelectItem key={v.id} value={v.id}>
                      {v.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <span className="text-xs text-muted-foreground">Loading…</span>
            )
          }
        />
        <Row
          label="Test voice"
          description="Hear a short sample phrase in the selected voice."
          control={
            <Button
              size="sm"
              variant="outline"
              onClick={() => void onTestVoice()}
              disabled={testingVoice}
            >
              {testingVoice ? "Speaking…" : "Test"}
            </Button>
          }
        />
      </Group>

      <Group title="Diagnostics">
        <Row
          label="Run test task"
          description="Captures your current screen and exercises the full Companion pipeline (screenshot → AI → pointer animation → spoken answer). No microphone needed — useful for verifying the feature end-to-end without holding the PTT key."
          control={
            <Button
              size="sm"
              variant="outline"
              onClick={() => void onRunTestTask()}
              disabled={runningTestTask || !companionEnabled}
            >
              <PlayCircle className="size-3.5" aria-hidden />
              {runningTestTask ? "Running…" : "Run test"}
            </Button>
          }
        />
      </Group>

      <Group title="Recent sessions">
        <CompanionSessionsViewer />
      </Group>
    </>
  );
}
