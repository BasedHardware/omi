'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ArrowLeft,
  Star,
  Clock,
  Calendar,
  CheckSquare,
  MessageSquare,
  FileText,
  MapPin,
  Sparkles,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatTime, formatDuration } from '@/lib/utils';
import { TranscriptView } from './TranscriptView';
import { AppSummaryCard } from './AppSummaryCard';
import { GenerateSummaryButton } from './GenerateSummaryButton';
import type { Conversation, ActionItem, AppResponse } from '@/types/conversation';

interface ConversationDetailPanelProps {
  conversationId: string;
  conversation: Conversation | null;
  loading: boolean;
  userName?: string;
  onBack?: () => void;
  onConversationUpdate?: (conversation: Conversation) => void;
}

type TabId = 'summary' | 'actions' | 'transcript' | 'location';

interface Tab {
  id: TabId;
  label: string;
  icon: React.ReactNode;
  count?: number;
  disabled?: boolean;
}

/**
 * Format date for display
 */
function formatDate(dateString: string | null): string {
  if (!dateString) return '';
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

/**
 * Calculate duration between two timestamps
 */
function calculateDuration(start: string | null, end: string | null): number {
  if (!start || !end) return 0;
  const startDate = new Date(start);
  const endDate = new Date(end);
  return Math.floor((endDate.getTime() - startDate.getTime()) / 1000);
}

/**
 * Action item component
 */
function ActionItemRow({ item }: { item: ActionItem }) {
  return (
    <div
      className={cn(
        'flex items-start gap-3 p-4 rounded-xl',
        'bg-bg-tertiary border border-bg-quaternary/50',
        item.completed && 'opacity-60'
      )}
    >
      <div
        className={cn(
          'w-5 h-5 rounded-md border-2 flex-shrink-0 mt-0.5',
          'flex items-center justify-center',
          item.completed
            ? 'bg-success border-success'
            : 'border-text-quaternary'
        )}
      >
        {item.completed && (
          <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
              clipRule="evenodd"
            />
          </svg>
        )}
      </div>
      <div className="flex-1">
        <span
          className={cn(
            'text-text-primary',
            item.completed && 'line-through text-text-tertiary'
          )}
        >
          {item.description}
        </span>
        {item.due_at && (
          <p className="text-xs text-text-quaternary mt-1">
            Due: {new Date(item.due_at).toLocaleDateString()}
          </p>
        )}
      </div>
    </div>
  );
}

/**
 * Summary tab content with app summaries
 */
interface SummaryTabProps {
  overview: string;
  category?: string;
  conversationId: string;
  appResults: AppResponse[];
  suggestedAppIds: string[];
  onGenerateComplete?: (conversation: Conversation) => void;
}

function SummaryTab({
  overview,
  category,
  conversationId,
  appResults,
  suggestedAppIds,
  onGenerateComplete,
}: SummaryTabProps) {
  const hasAppSummaries = appResults && appResults.length > 0;
  const hasSuggestedApps = suggestedAppIds && suggestedAppIds.length > 0;

  return (
    <div className="space-y-6">
      {/* Default Summary Section */}
      <div>
        {category && (
          <div className="mb-3">
            <span className="inline-flex px-3 py-1 rounded-full text-xs font-medium bg-purple-primary/10 text-purple-primary capitalize">
              {category}
            </span>
          </div>
        )}
        <p className="text-text-secondary leading-relaxed text-lg">
          {overview}
        </p>
      </div>

      {/* App Summaries Section */}
      {(hasAppSummaries || hasSuggestedApps) && (
        <div className="pt-4 border-t border-bg-tertiary">
          {/* Section Header with Generate Button */}
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-purple-primary" />
              <h3 className="text-sm font-medium text-text-primary">App Summaries</h3>
            </div>
            {hasSuggestedApps && (
              <GenerateSummaryButton
                conversationId={conversationId}
                suggestedAppIds={suggestedAppIds}
                existingAppResults={appResults}
                onGenerateComplete={onGenerateComplete}
              />
            )}
          </div>

          {/* App Summary Cards */}
          {hasAppSummaries && (
            <div className="space-y-3">
              {appResults.map((appResponse, index) => (
                <AppSummaryCard
                  key={`${appResponse.app_id}-${index}`}
                  appResponse={appResponse}
                />
              ))}
            </div>
          )}

          {/* Empty state for app summaries */}
          {!hasAppSummaries && hasSuggestedApps && (
            <p className="text-sm text-text-tertiary mt-2">
              No app summaries yet. Click the button above to generate one.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Action items tab content
 */
function ActionItemsTab({ items }: { items: ActionItem[] }) {
  const completedCount = items.filter(i => i.completed).length;

  return (
    <div className="space-y-4">
      {/* Progress indicator */}
      <div className="flex items-center gap-3 p-3 rounded-lg bg-bg-tertiary/50">
        <div className="flex-1">
          <div className="h-2 bg-bg-quaternary rounded-full overflow-hidden">
            <div
              className="h-full bg-success transition-all duration-300"
              style={{ width: `${(completedCount / items.length) * 100}%` }}
            />
          </div>
        </div>
        <span className="text-sm text-text-tertiary">
          {completedCount}/{items.length} completed
        </span>
      </div>

      {/* Action items list */}
      <div className="space-y-3">
        {items.map((item, index) => (
          <ActionItemRow key={index} item={item} />
        ))}
      </div>
    </div>
  );
}

/**
 * Location/Map tab content
 */
function LocationTab({ geolocation, address }: {
  geolocation: { latitude: number; longitude: number } | null;
  address?: string | null;
}) {
  if (!geolocation) {
    return (
      <div className="text-center py-12 text-text-tertiary">
        <MapPin className="w-12 h-12 mx-auto mb-4 opacity-50" />
        <p>No location data available for this conversation</p>
      </div>
    );
  }

  const { latitude, longitude } = geolocation;
  const mapUrl = `https://www.openstreetmap.org/export/embed.html?bbox=${longitude - 0.01}%2C${latitude - 0.01}%2C${longitude + 0.01}%2C${latitude + 0.01}&layer=mapnik&marker=${latitude}%2C${longitude}`;
  const linkUrl = `https://www.openstreetmap.org/?mlat=${latitude}&mlon=${longitude}#map=15/${latitude}/${longitude}`;

  return (
    <div className="space-y-4">
      {/* Address if available */}
      {address && (
        <div className="flex items-start gap-3 p-4 rounded-xl bg-bg-tertiary">
          <MapPin className="w-5 h-5 text-purple-primary flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-text-primary font-medium">Location</p>
            <p className="text-text-secondary text-sm">{address}</p>
          </div>
        </div>
      )}

      {/* Map embed */}
      <div className="rounded-xl overflow-hidden border border-bg-tertiary">
        <iframe
          src={mapUrl}
          width="100%"
          height="300"
          style={{ border: 0 }}
          loading="lazy"
          referrerPolicy="no-referrer-when-downgrade"
          title="Conversation location"
        />
      </div>

      {/* Coordinates and link */}
      <div className="flex items-center justify-between text-sm">
        <span className="text-text-quaternary">
          {latitude.toFixed(6)}, {longitude.toFixed(6)}
        </span>
        <a
          href={linkUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-purple-primary hover:text-purple-secondary transition-colors"
        >
          Open in OpenStreetMap
        </a>
      </div>
    </div>
  );
}

/**
 * Loading skeleton
 */
function DetailSkeleton() {
  return (
    <div className="p-6 animate-pulse">
      {/* Header */}
      <div className="flex items-start gap-4 mb-6">
        <div className="w-14 h-14 rounded-2xl bg-bg-tertiary" />
        <div className="flex-1">
          <div className="h-6 w-3/4 bg-bg-tertiary rounded mb-2" />
          <div className="flex gap-3">
            <div className="h-4 w-24 bg-bg-tertiary rounded" />
            <div className="h-4 w-20 bg-bg-tertiary rounded" />
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-6">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-10 w-24 bg-bg-tertiary rounded-lg" />
        ))}
      </div>

      {/* Content */}
      <div className="space-y-3">
        <div className="h-4 w-full bg-bg-tertiary rounded" />
        <div className="h-4 w-5/6 bg-bg-tertiary rounded" />
        <div className="h-4 w-4/6 bg-bg-tertiary rounded" />
      </div>
    </div>
  );
}

export function ConversationDetailPanel({
  conversationId,
  conversation,
  loading,
  userName,
  onBack,
  onConversationUpdate,
}: ConversationDetailPanelProps) {
  const [activeTab, setActiveTab] = useState<TabId>('summary');

  if (loading || !conversation) {
    return <DetailSkeleton />;
  }

  const { structured, transcript_segments, geolocation } = conversation;
  const duration = calculateDuration(conversation.started_at, conversation.finished_at);
  const actionItems = structured.action_items || [];
  const hasActionItems = actionItems.length > 0;
  const hasTranscript = transcript_segments && transcript_segments.length > 0;
  const hasLocation = geolocation && geolocation.latitude && geolocation.longitude;

  // Build tabs array based on available content
  const tabs: Tab[] = [
    {
      id: 'summary',
      label: 'Summary',
      icon: <FileText className="w-4 h-4" />,
      disabled: !structured.overview,
    },
    {
      id: 'actions',
      label: 'Actions',
      icon: <CheckSquare className="w-4 h-4" />,
      count: actionItems.length,
      disabled: !hasActionItems,
    },
    {
      id: 'transcript',
      label: 'Transcript',
      icon: <MessageSquare className="w-4 h-4" />,
      count: transcript_segments?.length || 0,
      disabled: !hasTranscript,
    },
    {
      id: 'location',
      label: 'Location',
      icon: <MapPin className="w-4 h-4" />,
      disabled: !hasLocation,
    },
  ];

  // Filter to only enabled tabs
  const enabledTabs = tabs.filter(tab => !tab.disabled);

  // Ensure active tab is valid
  if (!enabledTabs.find(t => t.id === activeTab)) {
    const firstEnabled = enabledTabs[0];
    if (firstEnabled && activeTab !== firstEnabled.id) {
      setActiveTab(firstEnabled.id);
    }
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex-shrink-0 p-4 lg:p-6 border-b border-bg-tertiary">
        <div className="flex items-start gap-4">
          {/* Back button (mobile only) */}
          {onBack && (
            <button
              onClick={onBack}
              className="lg:hidden p-2 -ml-2 rounded-lg hover:bg-bg-tertiary transition-colors"
              aria-label="Back to list"
            >
              <ArrowLeft className="w-5 h-5 text-text-secondary" />
            </button>
          )}

          {/* Emoji */}
          <div className="w-14 h-14 rounded-2xl bg-bg-tertiary flex items-center justify-center text-3xl flex-shrink-0">
            {structured.emoji || '💬'}
          </div>

          <div className="flex-1 min-w-0">
            {/* Title */}
            <h1 className="text-xl font-display font-semibold text-text-primary mb-2 line-clamp-2">
              {structured.title || 'Untitled Conversation'}
            </h1>

            {/* Meta info */}
            <div className="flex flex-wrap items-center gap-3 text-sm text-text-tertiary">
              {conversation.started_at && (
                <div className="flex items-center gap-1.5">
                  <Calendar className="w-4 h-4" />
                  <span>{formatDate(conversation.started_at)}</span>
                </div>
              )}
              {conversation.started_at && (
                <div className="flex items-center gap-1.5">
                  <Clock className="w-4 h-4" />
                  <span>{formatTime(new Date(conversation.started_at))}</span>
                </div>
              )}
              {duration > 0 && (
                <div className="flex items-center gap-1.5">
                  <MessageSquare className="w-4 h-4" />
                  <span>{formatDuration(duration)}</span>
                </div>
              )}
              {conversation.starred && (
                <div className="flex items-center gap-1.5 text-warning">
                  <Star className="w-4 h-4 fill-current" />
                  <span>Starred</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      {enabledTabs.length > 0 && (
        <div className="flex-shrink-0 px-4 lg:px-6 py-3 border-b border-bg-tertiary">
          <div className="flex gap-1">
            {enabledTabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  'flex items-center gap-2 px-3 py-2 rounded-lg',
                  'text-sm font-medium transition-all duration-150',
                  activeTab === tab.id
                    ? 'bg-purple-primary text-white'
                    : 'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary'
                )}
              >
                {tab.icon}
                <span>{tab.label}</span>
                {tab.count !== undefined && tab.count > 0 && (
                  <span
                    className={cn(
                      'px-1.5 py-0.5 rounded-full text-xs',
                      activeTab === tab.id
                        ? 'bg-white/20'
                        : 'bg-bg-tertiary'
                    )}
                  >
                    {tab.count}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-4 lg:p-6">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.15 }}
          >
            {activeTab === 'summary' && structured.overview && (
              <SummaryTab
                overview={structured.overview}
                category={structured.category}
                conversationId={conversationId}
                appResults={conversation.apps_results || []}
                suggestedAppIds={conversation.suggested_summarization_apps || []}
                onGenerateComplete={onConversationUpdate}
              />
            )}

            {activeTab === 'actions' && hasActionItems && (
              <ActionItemsTab items={actionItems} />
            )}

            {activeTab === 'transcript' && hasTranscript && (
              <TranscriptView segments={transcript_segments} userName={userName} />
            )}

            {activeTab === 'location' && (
              <LocationTab
                geolocation={geolocation}
                address={geolocation?.address}
              />
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
