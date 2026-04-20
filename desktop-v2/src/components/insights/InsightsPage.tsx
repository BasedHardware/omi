import { useEffect, useMemo, useState } from "react";
import {
  BookOpen,
  Check,
  CheckCircle2,
  Heart,
  Lightbulb,
  MessageSquare,
  MoreHorizontal,
  Search,
  Shapes,
  Trash2,
  TrendingUp,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  PageHeader,
  PageHeaderFilter,
  PageHeaderFilters,
} from "@/components/ui/page-header";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  INSIGHT_CATEGORIES,
  INSIGHT_CATEGORY_LABEL,
  StoredInsight,
  useInsightStore,
  type InsightCategory,
} from "@/stores/insightStore";
import { InsightCard } from "./InsightCard";
import { InsightDetailSheet } from "./InsightDetailSheet";

const CATEGORY_ICON: Record<InsightCategory, typeof Lightbulb> = {
  productivity: TrendingUp,
  communication: MessageSquare,
  learning: BookOpen,
  health: Heart,
  other: Shapes,
};

export function InsightsPage() {
  const insights = useInsightStore((s) => s.insights);
  const isLoading = useInsightStore((s) => s.isLoading);
  const query = useInsightStore((s) => s.query);
  const categoryFilter = useInsightStore((s) => s.categoryFilter);
  const showDismissed = useInsightStore((s) => s.showDismissed);
  const load = useInsightStore((s) => s.load);
  const setQuery = useInsightStore((s) => s.setQuery);
  const setCategoryFilter = useInsightStore((s) => s.setCategoryFilter);
  const setShowDismissed = useInsightStore((s) => s.setShowDismissed);
  const markAsRead = useInsightStore((s) => s.markAsRead);
  const markAllRead = useInsightStore((s) => s.markAllRead);
  const dismissInsight = useInsightStore((s) => s.dismissInsight);
  const deleteInsight = useInsightStore((s) => s.deleteInsight);
  const clearAll = useInsightStore((s) => s.clearAll);
  const filtered = useInsightStore((s) => s.filtered)();
  const visibleCount = useInsightStore((s) => s.visible)().length;
  const unreadCount = useInsightStore((s) => s.unreadCount)();
  const countForCategory = useInsightStore((s) => s.countForCategory);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);

  useEffect(() => {
    load();
  }, [load]);

  const selected = useMemo<StoredInsight | null>(
    () => (selectedId ? insights.find((i) => i.id === selectedId) ?? null : null),
    [selectedId, insights],
  );

  const isEmpty = !isLoading && insights.length === 0;
  const isFiltered = query.trim().length > 0 || categoryFilter !== null;
  const hasResults = filtered.length > 0;

  const subtitle = visibleCount === 0
    ? "Proactive observations from your AI assistant"
    : unreadCount > 0
      ? `${visibleCount} total · ${unreadCount} new`
      : `${visibleCount} total`;

  return (
    <div className="insights-page">
      <PageHeader
        title="Insights"
        subtitle={subtitle}
        actions={
          <>
            {unreadCount > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => void markAllRead()}
              >
                <CheckCircle2 size={14} className="mr-1.5" />
                Mark all read
              </Button>
            )}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" aria-label="More">
                  <MoreHorizontal size={16} />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuCheckboxItem
                  checked={showDismissed}
                  onCheckedChange={(checked) => setShowDismissed(!!checked)}
                >
                  Show dismissed
                </DropdownMenuCheckboxItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  disabled={insights.length === 0}
                  onSelect={() => setConfirmClear(true)}
                  variant="destructive"
                >
                  <Trash2 size={14} />
                  Clear all history
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </>
        }
      >
        {insights.length > 0 && (
          <>
            <div className="insights-search">
              <Search size={14} className="insights-search-icon" />
              <input
                className="insights-search-input"
                placeholder="Search insights"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              {query.length > 0 && (
                <button
                  type="button"
                  className="insights-search-clear"
                  onClick={() => setQuery("")}
                  aria-label="Clear search"
                >
                  <X size={14} />
                </button>
              )}
            </div>
            <PageHeaderFilters>
              <PageHeaderFilter
                active={categoryFilter === null}
                onClick={() => setCategoryFilter(null)}
                count={countForCategory(null)}
              >
                All
              </PageHeaderFilter>
              {INSIGHT_CATEGORIES.map((category) => {
                const Icon = CATEGORY_ICON[category];
                return (
                  <PageHeaderFilter
                    key={category}
                    active={categoryFilter === category}
                    onClick={() => setCategoryFilter(category)}
                    count={countForCategory(category)}
                    icon={<Icon size={12} />}
                  >
                    {INSIGHT_CATEGORY_LABEL[category]}
                  </PageHeaderFilter>
                );
              })}
            </PageHeaderFilters>
          </>
        )}
      </PageHeader>

      <div className="insights-content">
        {isLoading && insights.length === 0 && (
          <div className="page-empty">Loading insights…</div>
        )}

        {isEmpty && (
          <div className="insights-empty">
            <div className="insights-empty-icon-wrap">
              <Lightbulb size={28} />
            </div>
            <h3>No insights yet</h3>
            <p>
              As Nooto observes what you're working on, non-obvious
              observations and shortcuts will show up here. Keep Rewind on
              to let the Insight Assistant gather context.
            </p>
          </div>
        )}

        {!isEmpty && !hasResults && (
          <div className="insights-empty">
            <div className="insights-empty-icon-wrap">
              <Search size={24} />
            </div>
            <h3>No matches</h3>
            <p>Try a different search or clear the filters.</p>
            {isFiltered && (
              <div className="insights-empty-actions">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    setQuery("");
                    setCategoryFilter(null);
                  }}
                >
                  Clear filters
                </Button>
              </div>
            )}
          </div>
        )}

        {hasResults && (
          <div className="insights-list">
            {filtered.map((insight) => (
              <InsightCard
                key={insight.id}
                insight={insight}
                categoryIcon={CATEGORY_ICON[insight.category]}
                onOpen={() => {
                  if (!insight.isRead) void markAsRead(insight.id);
                  setSelectedId(insight.id);
                }}
                onDismiss={() => void dismissInsight(insight.id)}
                onDelete={() => void deleteInsight(insight.id)}
              />
            ))}
          </div>
        )}
      </div>

      <InsightDetailSheet
        insight={selected}
        categoryIcon={selected ? CATEGORY_ICON[selected.category] : Lightbulb}
        onClose={() => setSelectedId(null)}
      />

      <Dialog
        open={confirmClear}
        onOpenChange={(open) => setConfirmClear(open)}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Clear all insights?</DialogTitle>
            <DialogDescription>
              This removes every insight from your history. The action can't
              be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="ghost"
              onClick={() => setConfirmClear(false)}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                void clearAll();
                setConfirmClear(false);
              }}
            >
              <Check size={14} className="mr-1.5" />
              Clear all
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
