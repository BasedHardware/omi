"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DragEvent, PointerEvent, ReactNode } from "react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { GripVertical, Move } from "lucide-react";

// 12-column grid with fixed row height so both axes snap to tiles,
// giving the layout PostHog/Mixpanel-style rectangle behavior.
export const GRID_COLS = 12;
export const GRID_ROW_HEIGHT = 90; // px
export const GRID_GAP = 16; // px — matches Tailwind gap-4

const GHOST_TRAILING_ROWS = 3;

export type ColSpan = 3 | 4 | 6 | 8 | 9 | 12;
const COL_VALUES: ColSpan[] = [3, 4, 6, 8, 9, 12];
const MIN_ROWS = 2;
const MAX_ROWS = 8;

export interface ChartLayout {
  cols: ColSpan;
  rows: number;
}

export interface ChartItem {
  id: string;
  title: string;
  subtitle?: string;
  icon?: ReactNode;
  initialLayout?: Partial<ChartLayout>;
  render: (layout: ChartLayout) => ReactNode;
}

interface GridProps {
  storageKey: string;
  items: ChartItem[];
  className?: string;
}

interface PersistedLayout {
  order: string[];
  layouts: Record<string, ChartLayout>;
}

const DEFAULT_LAYOUT: ChartLayout = { cols: 3, rows: 3 };

function clampRows(n: number): number {
  if (!Number.isFinite(n)) return DEFAULT_LAYOUT.rows;
  return Math.max(MIN_ROWS, Math.min(MAX_ROWS, Math.round(n)));
}

function snapCols(n: number): ColSpan {
  let best: ColSpan = COL_VALUES[0];
  let bestDist = Math.abs(n - best);
  for (const c of COL_VALUES) {
    const d = Math.abs(n - c);
    if (d < bestDist) {
      best = c;
      bestDist = d;
    }
  }
  return best;
}

function defaultLayoutFor(item: ChartItem): ChartLayout {
  return {
    cols: snapCols(Number(item.initialLayout?.cols ?? DEFAULT_LAYOUT.cols)),
    rows: clampRows(Number(item.initialLayout?.rows ?? DEFAULT_LAYOUT.rows)),
  };
}

function readStored(storageKey: string): PersistedLayout | null {
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PersistedLayout;
    if (!Array.isArray(parsed.order) || typeof parsed.layouts !== "object") return null;
    return parsed;
  } catch {
    return null;
  }
}

function mergeOrder(stored: string[] | undefined, itemIds: string[]): string[] {
  const valid = new Set(itemIds);
  const kept = (stored ?? []).filter((id) => valid.has(id));
  const missing = itemIds.filter((id) => !kept.includes(id));
  return [...kept, ...missing];
}

function sanitizeLayout(l: Partial<ChartLayout> | undefined, fallback: ChartLayout): ChartLayout {
  return {
    cols: snapCols(Number(l?.cols ?? fallback.cols)),
    rows: clampRows(Number(l?.rows ?? fallback.rows)),
  };
}

function moveBefore(order: string[], draggedId: string, targetId: string): string[] {
  if (draggedId === targetId) return order;
  const without = order.filter((id) => id !== draggedId);
  const idx = without.indexOf(targetId);
  if (idx === -1) return order;
  const next = [...without];
  next.splice(idx, 0, draggedId);
  return next;
}

// Walk ordered items, placing each at the first available slot, to compute
// how many rows the layout currently occupies. Used to size the ghost lattice.
function computeRowsUsed(items: ChartItem[], layouts: Record<string, ChartLayout>): number {
  let topRow = 0;
  let cursor = 0;
  let maxRow = 0;
  for (const item of items) {
    const l = layouts[item.id];
    if (!l) continue;
    if (cursor + l.cols > GRID_COLS) {
      topRow += 1;
      cursor = 0;
    }
    const end = topRow + l.rows;
    if (end > maxRow) maxRow = end;
    cursor += l.cols;
    if (cursor >= GRID_COLS) {
      topRow += 1;
      cursor = 0;
    }
  }
  return Math.max(1, maxRow);
}

function ChartCard({
  item,
  layout,
  dragging,
  interacting,
  onLayoutChange,
  onInteractionChange,
  onDragStart,
  onDragOverCard,
  onDropOnCard,
  onDragEnd,
}: {
  item: ChartItem;
  layout: ChartLayout;
  dragging: boolean;
  interacting: boolean;
  onLayoutChange: (l: ChartLayout) => void;
  onInteractionChange: (active: boolean) => void;
  onDragStart: (id: string) => void;
  onDragOverCard: (e: DragEvent<HTMLElement>) => void;
  onDropOnCard: (id: string) => void;
  onDragEnd: () => void;
}) {
  const cardRef = useRef<HTMLDivElement | null>(null);
  const resizeRef = useRef<{
    pointerId: number;
    x: number;
    y: number;
    cols: ColSpan;
    rows: number;
    cardWidth: number;
  } | null>(null);

  const startResize = (e: PointerEvent<HTMLButtonElement>) => {
    e.preventDefault();
    e.stopPropagation();
    const rect = cardRef.current?.getBoundingClientRect();
    resizeRef.current = {
      pointerId: e.pointerId,
      x: e.clientX,
      y: e.clientY,
      cols: layout.cols,
      rows: layout.rows,
      cardWidth: Math.max(rect?.width ?? 1, 1),
    };
    e.currentTarget.setPointerCapture(e.pointerId);
    onInteractionChange(true);
  };

  const updateResize = (e: PointerEvent<HTMLButtonElement>) => {
    const start = resizeRef.current;
    if (!start || start.pointerId !== e.pointerId) return;

    const perCol = start.cardWidth / start.cols;
    const colDelta = Math.round((e.clientX - start.x) / perCol);
    const nextCols = snapCols(start.cols + colDelta);
    const rowDelta = Math.round((e.clientY - start.y) / (GRID_ROW_HEIGHT + GRID_GAP));
    const nextRows = clampRows(start.rows + rowDelta);

    if (nextCols !== layout.cols || nextRows !== layout.rows) {
      onLayoutChange({ cols: nextCols, rows: nextRows });
    }
  };

  const endResize = (e: PointerEvent<HTMLButtonElement>) => {
    const start = resizeRef.current;
    if (start?.pointerId === e.pointerId) {
      resizeRef.current = null;
      try {
        e.currentTarget.releasePointerCapture(e.pointerId);
      } catch {
        // pointer capture may already be released
      }
      onInteractionChange(false);
    }
  };

  const pixelHeight = layout.rows * GRID_ROW_HEIGHT + (layout.rows - 1) * GRID_GAP;

  return (
    <Card
      ref={cardRef}
      className={cn(
        "relative flex min-w-0 select-none flex-col gap-2 p-4 transition-shadow",
        dragging && "opacity-50 ring-2 ring-primary/40",
        interacting && !dragging && "ring-1 ring-primary/30",
      )}
      style={{
        gridColumn: `span ${layout.cols} / span ${layout.cols}`,
        gridRow: `span ${layout.rows} / span ${layout.rows}`,
        minHeight: pixelHeight,
      }}
      onDragOver={onDragOverCard}
      onDrop={() => onDropOnCard(item.id)}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex items-center gap-2">
          <button
            type="button"
            draggable
            aria-label={`Move ${item.title}`}
            title="Drag to move"
            className="flex h-6 w-6 shrink-0 cursor-grab items-center justify-center rounded-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground active:cursor-grabbing"
            onDragStart={(e) => {
              e.dataTransfer.effectAllowed = "move";
              e.dataTransfer.setData("text/plain", item.id);
              onDragStart(item.id);
            }}
            onDragEnd={onDragEnd}
          >
            <Move className="h-3.5 w-3.5" />
          </button>
          {item.icon && <span className="shrink-0 text-muted-foreground">{item.icon}</span>}
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold tracking-tight">{item.title}</h3>
            {item.subtitle && (
              <p className="line-clamp-1 text-xs text-muted-foreground">{item.subtitle}</p>
            )}
          </div>
        </div>
      </div>

      <div className="min-h-0 min-w-0 flex-1">{item.render(layout)}</div>

      <button
        type="button"
        aria-label={`Resize ${item.title}`}
        title="Drag to resize"
        className="absolute bottom-1.5 right-1.5 flex h-5 w-5 cursor-nwse-resize items-center justify-center rounded-sm bg-background/80 text-muted-foreground opacity-60 ring-1 ring-border/60 backdrop-blur hover:opacity-100"
        onPointerDown={startResize}
        onPointerMove={updateResize}
        onPointerUp={endResize}
        onPointerCancel={endResize}
      >
        <GripVertical className="h-3 w-3 rotate-45" />
      </button>
    </Card>
  );
}

export function ResizableChartGrid({ storageKey, items, className }: GridProps) {
  const itemIds = useMemo(() => items.map((i) => i.id), [items]);
  const itemMap = useMemo(() => new Map(items.map((i) => [i.id, i])), [items]);

  const [order, setOrder] = useState(itemIds);
  const [layouts, setLayouts] = useState<Record<string, ChartLayout>>(() =>
    Object.fromEntries(items.map((i) => [i.id, defaultLayoutFor(i)])),
  );
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [interactingCount, setInteractingCount] = useState(0);

  useEffect(() => {
    const stored = readStored(storageKey);
    setOrder(mergeOrder(stored?.order, itemIds));
    setLayouts((cur) => {
      const next: Record<string, ChartLayout> = {};
      for (const item of items) {
        const fallback = cur[item.id] ?? defaultLayoutFor(item);
        next[item.id] = sanitizeLayout(stored?.layouts?.[item.id] ?? fallback, defaultLayoutFor(item));
      }
      return next;
    });
    setHydrated(true);
  }, [itemIds, items, storageKey]);

  useEffect(() => {
    if (!hydrated) return;
    try {
      localStorage.setItem(storageKey, JSON.stringify({ order, layouts }));
    } catch {
      // localStorage may be unavailable; in-session state still works.
    }
  }, [hydrated, layouts, order, storageKey]);

  const updateLayout = useCallback((id: string, next: ChartLayout) => {
    setLayouts((cur) => ({ ...cur, [id]: next }));
  }, []);

  const handleDrop = useCallback((targetId: string) => {
    setOrder((cur) => (draggingId ? moveBefore(cur, draggingId, targetId) : cur));
    setDraggingId(null);
  }, [draggingId]);

  const handleInteraction = useCallback((active: boolean) => {
    setInteractingCount((c) => Math.max(0, c + (active ? 1 : -1)));
  }, []);

  const ordered = order
    .map((id) => itemMap.get(id))
    .filter((i): i is ChartItem => Boolean(i));

  const rowsUsed = computeRowsUsed(ordered, layouts);
  const ghostRows = rowsUsed + GHOST_TRAILING_ROWS;
  const interacting = interactingCount > 0 || draggingId != null;

  const containerStyle = {
    display: "grid",
    gridTemplateColumns: `repeat(${GRID_COLS}, minmax(0, 1fr))`,
    gridAutoRows: `${GRID_ROW_HEIGHT}px`,
    gap: `${GRID_GAP}px`,
  } as const;

  return (
    <div className={cn("relative", className)}>
      {/* Ghost lattice — faint tiles showing where charts can snap */}
      <div aria-hidden className="pointer-events-none absolute inset-0" style={containerStyle}>
        {Array.from({ length: ghostRows * GRID_COLS }).map((_, i) => (
          <div
            key={i}
            className={cn(
              "rounded-md border border-dashed transition-colors",
              interacting
                ? "border-primary/30 bg-primary/5"
                : "border-border/40 bg-muted/20",
            )}
          />
        ))}
      </div>

      {/* Real chart cards */}
      <div className="relative" style={containerStyle}>
        {ordered.map((item) => (
          <ChartCard
            key={item.id}
            item={item}
            layout={layouts[item.id] ?? defaultLayoutFor(item)}
            dragging={draggingId === item.id}
            interacting={interacting}
            onLayoutChange={(l) => updateLayout(item.id, l)}
            onInteractionChange={handleInteraction}
            onDragStart={setDraggingId}
            onDragOverCard={(e) => {
              if (draggingId) {
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
              }
            }}
            onDropOnCard={handleDrop}
            onDragEnd={() => setDraggingId(null)}
          />
        ))}
      </div>
    </div>
  );
}
