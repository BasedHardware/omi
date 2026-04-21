import { useEffect, useMemo, useState } from "react";
import { Search, Loader2 } from "lucide-react";
import { Input } from "../ui/input";
import { useAppStore } from "../../stores/appStore";
import {
  CAPABILITY,
  CAPABILITY_LABELS,
  type OmiApp,
} from "../../types/app";
import { AppCard } from "./AppCard";
import { AppDetailDialog } from "./AppDetailDialog";
import {
  PageHeader,
  PageHeaderFilter,
  PageHeaderFilters,
} from "../ui/page-header";

const CAPABILITY_FILTERS = [
  { id: null, label: "All" },
  { id: CAPABILITY.memories, label: CAPABILITY_LABELS[CAPABILITY.memories] },
  { id: CAPABILITY.chat, label: CAPABILITY_LABELS[CAPABILITY.chat] },
  { id: CAPABILITY.external, label: CAPABILITY_LABELS[CAPABILITY.external] },
  { id: CAPABILITY.proactive, label: CAPABILITY_LABELS[CAPABILITY.proactive] },
] as const;

export function AppsPage() {
  const apps = useAppStore((s) => s.apps);
  const isLoading = useAppStore((s) => s.isLoading);
  const loadApps = useAppStore((s) => s.loadApps);
  const searchQuery = useAppStore((s) => s.searchQuery);
  const setSearchQuery = useAppStore((s) => s.setSearchQuery);
  const selectedCapability = useAppStore((s) => s.selectedCapability);
  const setSelectedCapability = useAppStore((s) => s.setSelectedCapability);

  const [detailApp, setDetailApp] = useState<OmiApp | null>(null);

  useEffect(() => {
    loadApps();
  }, [loadApps]);

  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return apps.filter((app) => {
      if (app.deleted) return false;
      if (app.private && !app.enabled) return false;
      if (
        selectedCapability &&
        !app.capabilities.includes(selectedCapability)
      ) {
        return false;
      }
      if (q) {
        const haystack = `${app.name} ${app.author} ${app.description}`.toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
  }, [apps, searchQuery, selectedCapability]);

  const enabled = filtered.filter((a) => a.enabled);
  const available = filtered.filter((a) => !a.enabled);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <PageHeader
        title="Apps"
        subtitle="Enable apps to re-summarize conversations, add integrations, and more."
      >
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search apps"
            className="pl-9"
          />
        </div>

        <PageHeaderFilters>
          {CAPABILITY_FILTERS.map((f) => (
            <PageHeaderFilter
              key={f.label}
              active={selectedCapability === f.id}
              onClick={() => setSelectedCapability(f.id)}
            >
              {f.label}
            </PageHeaderFilter>
          ))}
        </PageHeaderFilters>
      </PageHeader>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {isLoading && apps.length === 0 ? (
          <div className="flex h-32 items-center justify-center text-muted-foreground">
            <Loader2 className="mr-2 size-4 animate-spin" />
            Loading apps…
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
            No apps found.
          </div>
        ) : (
          <div className="flex flex-col gap-8">
            {enabled.length > 0 && (
              <Section
                title={`Installed (${enabled.length})`}
                apps={enabled}
                onOpen={setDetailApp}
              />
            )}
            <Section
              title={enabled.length > 0 ? "Discover" : "All apps"}
              apps={available}
              onOpen={setDetailApp}
            />
          </div>
        )}
      </div>

      <AppDetailDialog app={detailApp} onClose={() => setDetailApp(null)} />
    </div>
  );
}

function Section({
  title,
  apps,
  onOpen,
}: {
  title: string;
  apps: OmiApp[];
  onOpen: (a: OmiApp) => void;
}) {
  if (apps.length === 0) return null;
  return (
    <div className="flex flex-col gap-3">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {apps.map((app) => (
          <AppCard key={app.id} app={app} onOpen={() => onOpen(app)} />
        ))}
      </div>
    </div>
  );
}
