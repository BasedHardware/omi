import { Star, Download, Loader2, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { Switch } from "../ui/switch";
import { useAppStore } from "../../stores/appStore";
import { CAPABILITY_LABELS } from "../../types/app";
import type { OmiApp } from "../../types/app";

export function AppCard({
  app,
  onOpen,
}: {
  app: OmiApp;
  onOpen: () => void;
}) {
  const enableApp = useAppStore((s) => s.enableApp);
  const disableApp = useAppStore((s) => s.disableApp);

  const onToggle = (next: boolean) => {
    if (next) enableApp(app.id);
    else disableApp(app.id);
  };

  const primaryCap = app.capabilities[0];

  return (
    <button
      type="button"
      onClick={onOpen}
      className={cn(
        "group flex flex-col gap-3 rounded-xl border border-border/60 bg-card p-4 text-left transition-colors",
        "hover:border-border hover:bg-accent/30",
      )}
    >
      <div className="flex items-start gap-3">
        <AppImage src={app.image} name={app.name} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-sm font-semibold text-foreground">
              {app.name}
            </h3>
            {app.enabled && (
              <span className="inline-flex items-center gap-1 rounded-full bg-green-500/10 px-1.5 py-0.5 text-[10px] font-medium text-green-600 dark:text-green-400">
                <Check className="size-2.5" />
                On
              </span>
            )}
          </div>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">
            {app.author || "Unknown"}
          </p>
        </div>
        <div onClick={(e) => e.stopPropagation()}>
          <Switch
            checked={app.enabled}
            onCheckedChange={onToggle}
            aria-label={app.enabled ? `Disable ${app.name}` : `Enable ${app.name}`}
          />
        </div>
      </div>

      <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">
        {app.description || ""}
      </p>

      <div className="flex items-center justify-between text-[11px] text-muted-foreground/80">
        <div className="flex items-center gap-3">
          {typeof app.rating_avg === "number" && app.rating_avg > 0 && (
            <span className="flex items-center gap-1">
              <Star className="size-3 fill-current" />
              {app.rating_avg.toFixed(1)}
            </span>
          )}
          {typeof app.installs === "number" && app.installs > 0 && (
            <span className="flex items-center gap-1">
              <Download className="size-3" />
              {formatInstalls(app.installs)}
            </span>
          )}
        </div>
        {primaryCap && (
          <span className="rounded-full border border-border/60 px-1.5 py-0.5">
            {CAPABILITY_LABELS[primaryCap] ?? primaryCap}
          </span>
        )}
      </div>
    </button>
  );
}

export function AppImage({
  src,
  name,
  size = 36,
}: {
  src: string;
  name: string;
  size?: number;
}) {
  const initial = name.charAt(0).toUpperCase();
  return (
    <div
      className="relative flex items-center justify-center overflow-hidden rounded-lg bg-muted text-sm font-semibold text-muted-foreground"
      style={{ width: size, height: size, flexShrink: 0 }}
    >
      {src ? (
        <img
          src={src}
          alt={name}
          className="size-full object-cover"
          onError={(e) => {
            (e.target as HTMLImageElement).style.display = "none";
          }}
        />
      ) : (
        <span>{initial}</span>
      )}
    </div>
  );
}

export function AppSwitchBusy() {
  return <Loader2 className="size-3 animate-spin" />;
}

function formatInstalls(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}
