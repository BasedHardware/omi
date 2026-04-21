import { useEffect, useMemo, useState } from "react";
import {
  BookOpen,
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
} from "../ui/page-header";
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
import { GroupedSection } from "../shared/GroupedSection";
import { InsightCard } from "./InsightCard";
import { InsightDetailSheet } from "./InsightDetailSheet";

const CATEGORY_ICON: Record<InsightCategory, typeof Lightbulb> = {
  productivity: TrendingUp,
  communication: MessageSquare,
  learning: BookOpen,
  health: Heart,
  other: Shapes,
};

const CATEGORY_ACCENT: Record<InsightCategory, string> = {
  productivity: "#3B82F6",
  communication: "#EC4899",
  learning: "#8B5CF6",
  health: "#F97316",
  other: "#94A3B8",
};

const MS_PER_DAY = 86_400_000;

function countThisWeek(items: { createdAt: string }[]): number {
  const cutoff = Date.now() - 7 * MS_PER_DAY;
  let n = 0;
  for (const i of items) {
    const t = Date.parse(i.createdAt);
    if (!Number.isNaN(t) && t >= cutoff) n += 1;
  }
  return n;
}

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
    () =>
      selectedId
        ? insights.find((i) => i.id === selectedId) ?? null
        : null,
    [selectedId, insights],
  );

  const thisWeek = useMemo(() => countThisWeek(insights), [insights]);
  const isEmpty = !isLoading && insights.length === 0;
  const isFiltered = query.trim().length > 0 || categoryFilter !== null;

  // Group filtered insights by category, preserve category order by count.
  const grouped = useMemo(() => {
    const map: Record<InsightCategory, StoredInsight[]> = {
      productivity: [],
      communication: [],
      learning: [],
      health: [],
      other: [],
    };
    for (const i of filtered) {
      map[i.category].push(i);
    }
    const isBrowsing = !isFiltered;
    return INSIGHT_CATEGORIES
      .map((cat) => ({ category: cat, items: map[cat] }))
      .filter((g) => g.items.length > 0)
      .sort((a, b) => {
        // When filtering, keep insight-backend order (already sorted by date).
        // When browsing, largest category first, same as Memories' themes.
        if (!isBrowsing) return 0;
        return b.items.length - a.items.length;
      });
  }, [filtered, isFiltered]);

  const subtitle =
    visibleCount === 0
      ? "Proactive observations from your AI assistant"
      : [
          `${visibleCount} insights`,
          thisWeek > 0 ? `${thisWeek} this week` : null,
          unreadCount > 0 ? `${unreadCount} new` : null,
        ]
          .filter(Boolean)
          .join(" · ");

  return (
    <div className="memories-page">
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
            <PageHeaderFilters>
              <PageHeaderFilter
                active={categoryFilter === null}
                onClick={() => setCategoryFilter(null)}
                count={countForCategory(null)}
              >
                All
              </PageHeaderFilter>
              {INSIGHT_CATEGORIES.map((cat) => {
                const count = countForCategory(cat);
                if (count === 0) return null;
                const Icon = CATEGORY_ICON[cat];
                return (
                  <PageHeaderFilter
                    key={cat}
                    active={categoryFilter === cat}
                    onClick={() => setCategoryFilter(cat)}
                    count={count}
                    icon={<Icon size={12} />}
                  >
                    {INSIGHT_CATEGORY_LABEL[cat]}
                  </PageHeaderFilter>
                );
              })}
            </PageHeaderFilters>
            <div className="memories-search">
              <Search className="memories-search-icon" />
              <input
                className="memories-search-input"
                placeholder="Search insights"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              {query.length > 0 && (
                <button
                  type="button"
                  className="memories-search-clear"
                  onClick={() => setQuery("")}
                  aria-label="Clear search"
                >
                  <X className="memories-search-clear-icon" />
                </button>
              )}
            </div>
          </>
        )}
      </PageHeader>

      <div className="memories-content">
        {isLoading && insights.length === 0 && (
          <div className="page-empty">Loading insights...</div>
        )}

        {isEmpty && (
          <div className="page-empty">
            No insights yet. As Nooto observes what you're working on,
            proactive observations will appear here.
          </div>
        )}

        {insights.length > 0 && grouped.length === 0 && (
          <div className="page-empty">
            No insights match your filters.
          </div>
        )}

        {grouped.length > 0 && (
          <div className="themed-sections">
            {grouped.map(({ category, items }, i) => {
              const Icon = CATEGORY_ICON[category];
              const preview = items[0]?.content ?? "";
              return (
                <GroupedSection
                  key={category}
                  icon={Icon}
                  label={INSIGHT_CATEGORY_LABEL[category]}
                  count={items.length}
                  preview={preview}
                  accent={CATEGORY_ACCENT[category]}
                  defaultOpen={i === 0}
                >
                  {items.map((insight) => (
                    <InsightCard
                      key={insight.id}
                      insight={insight}
                      categoryIcon={Icon}
                      onOpen={() => {
                        if (!insight.isRead) void markAsRead(insight.id);
                        setSelectedId(insight.id);
                      }}
                      onDismiss={() => void dismissInsight(insight.id)}
                      onDelete={() => void deleteInsight(insight.id)}
                    />
                  ))}
                </GroupedSection>
              );
            })}
          </div>
        )}
      </div>

      <InsightDetailSheet
        insight={selected}
        categoryIcon={selected ? CATEGORY_ICON[selected.category] : Lightbulb}
        onClose={() => setSelectedId(null)}
      />

      <Dialog open={confirmClear} onOpenChange={(open) => setConfirmClear(open)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Clear all insights?</DialogTitle>
            <DialogDescription>
              This removes every insight from your history. The action can't be
              undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmClear(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                void clearAll();
                setConfirmClear(false);
              }}
            >
              Clear all
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
