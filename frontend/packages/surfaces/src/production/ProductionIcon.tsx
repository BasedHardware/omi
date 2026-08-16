import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  Ellipsis,
  History,
  Inbox,
  LayoutGrid,
  Library,
  ListChecks,
  LoaderCircle,
  MessageCircle,
  Mic,
  Monitor,
  Paperclip,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings,
  Star,
  WifiOff,
  X,
  type LucideIcon,
} from "lucide-react";

/**
 * The deliberately small, audited icon vocabulary used by production surfaces.
 * Keeping this map explicit gives us tree-shaking and prevents route authors from
 * falling back to emoji, Unicode approximations, or one-off SVG paths.
 */
export type ProductionIconName =
  | "alert"
  | "apps"
  | "attach"
  | "back"
  | "calendar"
  | "check"
  | "close"
  | "conversations"
  | "forward"
  | "history"
  | "inbox"
  | "library"
  | "loading"
  | "microphone"
  | "more"
  | "offline"
  | "plus"
  | "refresh"
  | "screen"
  | "search"
  | "send"
  | "settings"
  | "star"
  | "tasks";

const productionIcons: Readonly<Record<ProductionIconName, LucideIcon>> = {
  alert: CircleAlert,
  apps: LayoutGrid,
  attach: Paperclip,
  back: ChevronLeft,
  calendar: CalendarDays,
  check: CircleCheck,
  close: X,
  conversations: MessageCircle,
  forward: ChevronRight,
  history: History,
  inbox: Inbox,
  library: Library,
  loading: LoaderCircle,
  microphone: Mic,
  more: Ellipsis,
  offline: WifiOff,
  plus: Plus,
  refresh: RefreshCw,
  screen: Monitor,
  search: Search,
  send: Send,
  settings: Settings,
  star: Star,
  tasks: ListChecks,
};

export function ProductionIcon({
  name,
  size = 20,
  strokeWidth = 1.8,
  className = "",
  filled = false,
}: {
  name: ProductionIconName;
  size?: number;
  strokeWidth?: number;
  className?: string;
  filled?: boolean;
}): React.JSX.Element {
  const Icon = productionIcons[name];
  return (
    <Icon
      aria-hidden="true"
      focusable="false"
      className={`production-icon${className ? ` ${className}` : ""}`}
      size={size}
      strokeWidth={strokeWidth}
      fill={filled ? "currentColor" : "none"}
    />
  );
}
