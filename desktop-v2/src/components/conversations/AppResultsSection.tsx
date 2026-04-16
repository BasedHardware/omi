import { useMemo, useState } from "react";
import { RefreshCw, Loader2, Sparkles } from "lucide-react";
import { Button } from "../ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../ui/tabs";
import { useAppStore } from "../../stores/appStore";
import { worksWithMemories } from "../../types/app";
import type { OmiApp } from "../../types/app";
import type { Conversation } from "../../stores/conversationStore";
import { AppImage } from "../apps/AppCard";
import { GenerativeMarkdown } from "../generative-ui/GenerativeMarkdown";

/**
 * Empty-state strip shown above the inline transcript when the user has
 * memory-capable apps installed but hasn't reprocessed this conversation yet.
 */
export function AppInsightsEmpty({ conversation }: { conversation: Conversation }) {
  const apps = useAppStore((s) => s.apps);
  const hasMemoryApps = apps.some(worksWithMemories);
  if (!hasMemoryApps) return null;

  return (
    <div className="flex items-center justify-between gap-3 border-b border-border/50 px-6 py-3">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Sparkles className="size-3.5" />
        <span>Run an app to get a custom summary.</span>
      </div>
      <ReprocessButton conversation={conversation} />
    </div>
  );
}

/**
 * Full-page app insight rendering. If multiple apps have produced results,
 * render a Tabs switcher. Otherwise render the single result directly.
 */
export function AppResultsFull({ conversation }: { conversation: Conversation }) {
  const apps = useAppStore((s) => s.apps);
  const results = conversation.apps_results ?? [];

  const [activeId, setActiveId] = useState<string | undefined>(() =>
    results[0] ? String(results[0].id) : undefined,
  );

  const tabs = useMemo(
    () =>
      results.map((r) => ({
        result: r,
        app: apps.find((a) => a.id === r.app_id),
      })),
    [results, apps],
  );

  if (tabs.length === 0) return null;

  if (tabs.length === 1) {
    const { result, app } = tabs[0];
    return (
      <section className="px-8 pb-8 pt-6">
        <ResultHeader
          app={app}
          showReprocess
          conversation={conversation}
        />
        <GenerativeMarkdown
          content={result.content}
          className="prose-lg max-w-none text-foreground/90"
        />
      </section>
    );
  }

  const activeTab =
    tabs.find((t) => String(t.result.id) === activeId) ?? tabs[0];

  return (
    <section className="px-8 pb-8 pt-6">
      <Tabs
        value={String(activeTab.result.id)}
        onValueChange={setActiveId}
      >
        <div className="mb-5 flex items-center justify-between gap-3">
          <TabsList variant="line" className="h-9 min-w-0 flex-1 justify-start overflow-x-auto">
            {tabs.map(({ result, app }) => (
              <TabsTrigger
                key={result.id}
                value={String(result.id)}
                className="gap-2 px-3"
              >
                <AppImage src={app?.image ?? ""} name={app?.name ?? "App"} size={18} />
                <span className="max-w-[160px] truncate">{app?.name ?? "App"}</span>
              </TabsTrigger>
            ))}
          </TabsList>
          <ReprocessButton conversation={conversation} />
        </div>

        {tabs.map(({ result }) => (
          <TabsContent key={result.id} value={String(result.id)} className="mt-0">
            <GenerativeMarkdown
              content={result.content}
              className="prose-lg max-w-none text-foreground/90"
            />
          </TabsContent>
        ))}
      </Tabs>
    </section>
  );
}

function ResultHeader({
  app,
  showReprocess,
  conversation,
}: {
  app: OmiApp | undefined;
  showReprocess: boolean;
  conversation: Conversation;
}) {
  return (
    <header className="mb-5 flex items-center justify-between gap-3">
      <div className="flex items-center gap-3">
        <AppImage src={app?.image ?? ""} name={app?.name ?? "App"} size={32} />
        <div className="min-w-0">
          <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Summarized by
          </p>
          <p className="truncate text-sm font-semibold text-foreground">
            {app?.name ?? "App"}
          </p>
        </div>
      </div>
      {showReprocess && <ReprocessButton conversation={conversation} />}
    </header>
  );
}

function ReprocessButton({ conversation }: { conversation: Conversation }) {
  const apps = useAppStore((s) => s.apps);
  const isReprocessing = useAppStore((s) => s.isReprocessing);
  const reprocessingAppId = useAppStore((s) => s.reprocessingAppId);
  const reprocessConversation = useAppStore((s) => s.reprocessConversation);

  const enabledMemoryApps = apps.filter(
    (a) => a.enabled && worksWithMemories(a),
  );

  const onPick = async (app: OmiApp) => {
    await reprocessConversation(conversation.id, app.id);
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="xs"
          disabled={isReprocessing || enabledMemoryApps.length === 0}
        >
          {isReprocessing ? (
            <Loader2 className="size-3 animate-spin" />
          ) : (
            <RefreshCw className="size-3" />
          )}
          Reprocess
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        {enabledMemoryApps.length === 0 ? (
          <div className="p-3 text-xs text-muted-foreground">
            Enable apps with the Memories capability to reprocess conversations.
          </div>
        ) : (
          <>
            <DropdownMenuLabel className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              Run with app
            </DropdownMenuLabel>
            {enabledMemoryApps.map((app) => {
              const isBusy = reprocessingAppId === app.id;
              return (
                <DropdownMenuItem
                  key={app.id}
                  onSelect={() => void onPick(app)}
                  disabled={isReprocessing}
                  className="gap-2"
                >
                  <AppImage src={app.image} name={app.name} size={22} />
                  <span className="min-w-0 flex-1 truncate text-xs font-medium">
                    {app.name}
                  </span>
                  {isBusy && <Loader2 className="size-3 animate-spin" />}
                </DropdownMenuItem>
              );
            })}
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
