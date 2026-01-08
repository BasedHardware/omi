'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { CalendarDays, Loader2, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useRecaps } from '@/hooks/useRecaps';
import { useLocalStorage } from '@/hooks/useLocalStorage';
import { RecapDateGroup } from './RecapDateGroup';
import { RecapDetailPanel, RecapDetailPanelSkeleton } from './RecapDetailPanel';
import { RecapCardSkeleton } from './RecapCard';
import { ResizeHandle } from '@/components/ui/ResizeHandle';
import type { DailySummary } from '@/types/recap';
import { useChat as useChatContext } from '@/components/chat/ChatContext';

// Panel width constraints (for left list panel)
const MIN_PANEL_WIDTH = 280;
const MAX_PANEL_WIDTH = 400;
const DEFAULT_PANEL_WIDTH = 320;

export function RecapSplitView() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedRecap, setSelectedRecap] = useState<DailySummary | null>(null);

  // Resizable panel width
  const [panelWidth, setPanelWidth] = useLocalStorage('omi-recap-panel-width', DEFAULT_PANEL_WIDTH);

  const {
    recaps,
    groupedRecaps,
    loading,
    error,
    hasMore,
    loadMore,
    refresh,
    removeRecap,
    getRecapDetail,
  } = useRecaps();

  // Chat context for passing selected recap info
  const { setContext } = useChatContext();

  // Set chat context when a recap is selected
  useEffect(() => {
    if (selectedRecap) {
      setContext({
        type: 'recap',
        id: selectedRecap.id,
        title: selectedRecap.headline || `Daily Recap - ${selectedRecap.date}`,
        summary: selectedRecap.overview,
      });
    } else {
      setContext(null);
    }
  }, [selectedRecap, setContext]);

  // Clear chat context when component unmounts
  useEffect(() => {
    return () => setContext(null);
  }, [setContext]);

  // Auto-select first recap on load
  useEffect(() => {
    if (!selectedId && !loading && recaps.length > 0) {
      setSelectedId(recaps[0].id);
      setSelectedRecap(recaps[0]);
    }
  }, [recaps, loading, selectedId]);

  // Handle recap selection
  const handleRecapClick = async (recap: DailySummary) => {
    setSelectedId(recap.id);
    setSelectedRecap(recap);

    // Optionally fetch full details
    const fullRecap = await getRecapDetail(recap.id);
    if (fullRecap) {
      setSelectedRecap(fullRecap);
    }
  };

  // Handle recap deletion
  const handleDelete = async (id: string) => {
    const success = await removeRecap(id);
    if (success) {
      // Select next recap or clear selection
      const currentIndex = recaps.findIndex((r) => r.id === id);
      const nextRecap = recaps[currentIndex + 1] || recaps[currentIndex - 1];
      if (nextRecap) {
        setSelectedId(nextRecap.id);
        setSelectedRecap(nextRecap);
      } else {
        setSelectedId(null);
        setSelectedRecap(null);
      }
    }
  };

  // Handle infinite scroll
  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    if (scrollHeight - scrollTop - clientHeight < 200 && hasMore && !loading) {
      loadMore();
    }
  };

  // Resize handler
  const handleResize = (delta: number) => {
    setPanelWidth((prev) =>
      Math.min(MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, prev + delta))
    );
  };

  // Error state
  if (error && recaps.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8">
        <p className="text-error mb-4">{error}</p>
        <button
          onClick={refresh}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-purple-primary text-white hover:bg-purple-secondary transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Retry
        </button>
      </div>
    );
  }

  // Empty state
  if (!loading && recaps.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8 text-center">
        <CalendarDays className="w-16 h-16 text-text-quaternary mb-4" />
        <h3 className="text-lg font-medium text-text-primary mb-2">
          No recaps yet
        </h3>
        <p className="text-sm text-text-tertiary max-w-sm">
          Daily recaps will appear here once you have enough conversations.
          Make sure daily summaries are enabled in your settings.
        </p>
      </div>
    );
  }

  const monthKeys = Object.keys(groupedRecaps);

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left panel: Recap list (fixed width) */}
      <div
        className="flex-shrink-0 flex flex-col overflow-hidden border-r border-bg-tertiary"
        style={{ width: panelWidth }}
      >
        {/* List header */}
        <div className="flex-shrink-0 p-4 border-b border-bg-tertiary">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-text-secondary">
              {recaps.length} recap{recaps.length !== 1 ? 's' : ''}
            </h2>
            <button
              onClick={refresh}
              disabled={loading}
              className={cn(
                'p-1.5 rounded-lg transition-colors',
                'hover:bg-bg-tertiary text-text-tertiary hover:text-text-primary',
                loading && 'animate-spin'
              )}
              title="Refresh"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Recap list with infinite scroll */}
        <div
          className="flex-1 overflow-y-auto p-4"
          onScroll={handleScroll}
        >
          {/* Loading skeleton */}
          {loading && recaps.length === 0 && (
            <div className="space-y-6">
              <div className="space-y-2">
                <div className="h-4 w-24 bg-bg-tertiary rounded animate-pulse" />
                <RecapCardSkeleton />
                <RecapCardSkeleton />
              </div>
              <div className="space-y-2">
                <div className="h-4 w-32 bg-bg-tertiary rounded animate-pulse" />
                <RecapCardSkeleton />
              </div>
            </div>
          )}

          {/* Grouped recaps */}
          {monthKeys.map((monthKey) => (
            <RecapDateGroup
              key={monthKey}
              monthLabel={monthKey}
              recaps={groupedRecaps[monthKey]}
              selectedId={selectedId}
              onRecapClick={handleRecapClick}
            />
          ))}

          {/* Load more indicator */}
          {loading && recaps.length > 0 && (
            <div className="flex justify-center py-4">
              <Loader2 className="w-5 h-5 text-purple-primary animate-spin" />
            </div>
          )}
        </div>
      </div>

      {/* Resize handle */}
      <ResizeHandle onResize={handleResize} />

      {/* Right panel: Detail view (fills remaining space) */}
      <div className="flex-1 min-w-0 overflow-hidden">
        <AnimatePresence mode="wait">
          {selectedId ? (
            <motion.div
              key={selectedId}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="h-full"
            >
              <RecapDetailPanel
                recapId={selectedId}
                recap={selectedRecap}
              />
            </motion.div>
          ) : (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="h-full flex items-center justify-center"
            >
              <div className="text-center p-8">
                <CalendarDays className="w-12 h-12 text-text-quaternary mx-auto mb-3" />
                <p className="text-text-tertiary">
                  Select a recap to view details
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
