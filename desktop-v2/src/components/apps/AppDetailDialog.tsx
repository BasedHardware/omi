import { Star, Download } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Button } from "../ui/button";
import { Switch } from "../ui/switch";
import { useAppStore } from "../../stores/appStore";
import { CAPABILITY_LABELS, worksExternally } from "../../types/app";
import type { OmiApp } from "../../types/app";
import { AppImage } from "./AppCard";

export function AppDetailDialog({
  app,
  onClose,
}: {
  app: OmiApp | null;
  onClose: () => void;
}) {
  const enableApp = useAppStore((s) => s.enableApp);
  const disableApp = useAppStore((s) => s.disableApp);
  const twoWaySync = useAppStore((s) =>
    app ? Boolean(s.twoWaySyncByAppId[app.id]) : false,
  );
  const setTwoWaySync = useAppStore((s) => s.setTwoWaySync);
  // Only external integrations (Jira/Linear/…) can write back to a source
  // tracker, so the toggle is hidden for chat-only or persona apps.
  const canTwoWaySync = !!app && app.enabled && worksExternally(app);

  return (
    <Dialog open={!!app} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-[520px]">
        {app && (
          <>
            <DialogHeader>
              <div className="flex items-start gap-3">
                <AppImage src={app.image} name={app.name} size={48} />
                <div className="min-w-0 flex-1">
                  <DialogTitle className="text-base">{app.name}</DialogTitle>
                  <p className="mt-1 text-xs text-muted-foreground">
                    by {app.author || "Unknown"}
                  </p>
                </div>
              </div>
            </DialogHeader>

            <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
              {typeof app.rating_avg === "number" && app.rating_avg > 0 && (
                <span className="flex items-center gap-1">
                  <Star className="size-3 fill-current" />
                  {app.rating_avg.toFixed(1)}
                  {typeof app.rating_count === "number" &&
                    app.rating_count > 0 && (
                      <span className="text-muted-foreground/70">
                        ({app.rating_count})
                      </span>
                    )}
                </span>
              )}
              {typeof app.installs === "number" && app.installs > 0 && (
                <span className="flex items-center gap-1">
                  <Download className="size-3" />
                  {app.installs.toLocaleString()} installs
                </span>
              )}
            </div>

            <div className="flex flex-wrap gap-1.5">
              {app.capabilities.map((cap) => (
                <span
                  key={cap}
                  className="rounded-full border border-border/60 bg-muted/40 px-2 py-0.5 text-[11px] text-muted-foreground"
                >
                  {CAPABILITY_LABELS[cap] ?? cap}
                </span>
              ))}
            </div>

            {app.description && (
              <p className="whitespace-pre-line text-sm leading-relaxed text-foreground/90">
                {app.description}
              </p>
            )}

            {canTwoWaySync && (
              <div className="flex items-start justify-between gap-3 rounded-lg border border-border/60 bg-muted/20 p-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium">Two-way sync</p>
                  <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">
                    Let Nooto mark tickets done in {app.name} when you complete
                    them from your Plan. Off by default.
                  </p>
                </div>
                <Switch
                  checked={twoWaySync}
                  onCheckedChange={(on) => setTwoWaySync(app.id, on)}
                  aria-label={`Two-way sync with ${app.name}`}
                />
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              {app.enabled ? (
                <Button
                  variant="outline"
                  onClick={() => {
                    disableApp(app.id);
                    onClose();
                  }}
                >
                  Disable
                </Button>
              ) : (
                <Button
                  onClick={() => {
                    enableApp(app.id);
                    onClose();
                  }}
                >
                  Enable
                </Button>
              )}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
