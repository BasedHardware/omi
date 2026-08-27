'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { useRouter } from '@tschk/moonshine-next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ArrowLeft,
  Star,
  Clock,
  Calendar,
  CheckSquare,
  MessageSquare,
  FileText,
  Sparkles,
  Volume2,
  RefreshCw,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatTime, formatDuration } from '@/lib/utils';
import { TranscriptView } from './TranscriptView';
import { ConversationActionsMenu } from './ConversationActionsMenu';
import { EditableTitle } from './EditableTitle';
import { SpeakerTagSheet } from './SpeakerTagSheet';
import { ManagePeopleModal } from './ManagePeopleModal';
import { AudioPlayer, AudioPlayerRef } from './AudioPlayer';
import { SummaryTab } from './SummaryTab';
import { ActionItemsTab } from './ActionItemsTab';
import { DetailSkeleton } from './DetailSkeleton';
import { formatConversationDate, conversationDurationSeconds } from '../model';
import { usePeople } from '../usePeople';
import { precacheConversationAudio, getConversationAudioUrls, updateSegmentText, reprocessConversation } from '../api';
import { MixpanelManager } from '@/lib/analytics/mixpanel';
import type {
  Conversation,
  TranscriptSegment,
  AudioFileUrlInfo,
} from '@/types/conversation';

interface ConversationDetailPanelProps {
  conversationId: string;
  conversation: Conversation | null;
  loading: boolean;
  userName?: string;
  onBack?: () => void;
  onConversationUpdate?: (conversation: Conversation) => void;
  onDelete?: () => void;
}

// Give a reprocess this long before we stop waiting and surface a failure, so a
// hung request can't leave the UI stuck on "Reprocessing…" indefinitely.
const REPROCESS_TIMEOUT_MS = 90_000;

type TabId = 'summary' | 'actions' | 'transcript';

interface Tab {
  id: TabId;
  label: string;
  icon: React.ReactNode;
  count?: number;
  disabled?: boolean;
}

export function ConversationDetailPanel({
  conversationId,
  conversation,
  loading,
  userName,
  onBack,
  onConversationUpdate,
  onDelete,
}: ConversationDetailPanelProps) {
  const [activeTab, setActiveTab] = useState<TabId>('summary');
  const [selectedSegment, setSelectedSegment] = useState<TranscriptSegment | null>(null);
  const [showTagSheet, setShowTagSheet] = useState(false);
  const [showManagePeople, setShowManagePeople] = useState(false);
  // Whether a transcript segment was edited this session (derived summary/search
  // is now stale until the conversation is reprocessed — see the nudge banner).
  const [transcriptEdited, setTranscriptEdited] = useState(false);
  const [isReprocessing, setIsReprocessing] = useState(false);
  // Set when a reprocess errors or times out, so the failure is surfaced to the
  // user (not just console) and they can retry — the summary stays stale.
  const [reprocessFailed, setReprocessFailed] = useState(false);
  // Serialized transcript-edit save queue. Segment edits are persisted one at a
  // time so concurrent PATCHes can't lose-update the backend's read-modify-write
  // of the whole segments array (each save reads the state left by the previous
  // one). `saveBatch` drives the "Saving X of N" progress UI.
  const saveQueueRef = useRef<
    Array<{ segmentId: string; text: string; prevText: string }>
  >([]);
  const processingRef = useRef(false);
  const [saveBatch, setSaveBatch] = useState<{
    total: number;
    done: number;
    savingId: string | null;
    failed: number;
  }>({ total: 0, done: 0, savingId: null, failed: 0 });
  const router = useRouter();
  const { people } = usePeople();

  // Refs holding the *currently displayed* conversation id and object, so async
  // completions (segment saves, reprocess) can (a) build optimistic updates from
  // the latest state and (b) bail out if the user switched conversations while a
  // request was in flight — otherwise a stale response would clobber the new
  // conversation's UI (displayed id vs. request id divergence).
  const convIdRef = useRef(conversationId);
  const conversationRef = useRef(conversation);
  useEffect(() => {
    convIdRef.current = conversationId;
    conversationRef.current = conversation;
  }, [conversationId, conversation]);

  // Reset all edit/save state when switching to a different conversation so
  // nothing leaks across (queued saves, progress, "edited" nudge, reprocessing).
  useEffect(() => {
    saveQueueRef.current = [];
    processingRef.current = false;
    setSaveBatch({ total: 0, done: 0, savingId: null, failed: 0 });
    setTranscriptEdited(false);
    setIsReprocessing(false);
    setReprocessFailed(false);
  }, [conversationId]);

  const isSavingSegments = saveBatch.total > saveBatch.done;

  // Audio state
  const audioPlayerRef = useRef<AudioPlayerRef>(null);
  const [audioAvailable, setAudioAvailable] = useState(false);
  const [fetchedAudioFiles, setFetchedAudioFiles] = useState<AudioFileUrlInfo[]>([]);
  const [currentPlaybackTime, setCurrentPlaybackTime] = useState<number | undefined>(
    undefined,
  );

  // Check audio availability for the conversation
  const audio_files = conversation?.audio_files || [];
  const hasAudioFiles = audio_files.length > 0;

  useEffect(() => {
    if (!conversation) return;
    const abortController = new AbortController();
    const signal = abortController.signal;

    async function checkAudioAvailability() {
      // Helper to map audio URLs to AudioFile format
      const mapAudioUrls = (urls: Awaited<ReturnType<typeof getConversationAudioUrls>>) =>
        urls.map((af) => ({
          id: af.id,
          duration: af.duration || 0,
          signed_url: af.signed_url,
          status: af.status,
        }));

      // If audio_files array has data, audio is available
      if (hasAudioFiles) {
        setAudioAvailable(true);

        // Try to get URLs immediately (might already be cached)
        const cachedUrls = await getConversationAudioUrls(conversationId, signal);
        if (signal.aborted) return;

        // Check if we got valid signed URLs
        if (cachedUrls && cachedUrls.length > 0 && cachedUrls[0].signed_url) {
          setFetchedAudioFiles(mapAudioUrls(cachedUrls));
          return;
        }

        // URLs not cached - trigger precache and wait
        await precacheConversationAudio(conversationId, signal);
        if (signal.aborted) return;

        // Fetch signed URLs after precaching
        const audioUrls = await getConversationAudioUrls(conversationId, signal);
        if (signal.aborted) return;

        if (audioUrls && audioUrls.length > 0) {
          setFetchedAudioFiles(mapAudioUrls(audioUrls));
        }
        return;
      }

      // Otherwise, try to fetch audio URLs with retries
      for (let attempt = 0; attempt < 3; attempt++) {
        if (signal.aborted) return;
        if (attempt > 0) {
          await new Promise((resolve) => setTimeout(resolve, 500));
        }

        const audioUrls = await getConversationAudioUrls(conversationId, signal);
        if (signal.aborted) return;

        if (audioUrls && audioUrls.length > 0) {
          setAudioAvailable(true);
          setFetchedAudioFiles(mapAudioUrls(audioUrls));
          return;
        }
      }
      setAudioAvailable(false);
    }

    checkAudioAvailability();
    return () => abortController.abort();
  }, [conversationId, conversation, hasAudioFiles]);

  const handleAudioTimeUpdate = useCallback((time: number) => {
    setCurrentPlaybackTime(time);
  }, []);

  const handleSeekTo = useCallback((time: number) => {
    audioPlayerRef.current?.seekTo(time);
    audioPlayerRef.current?.play();
  }, []);

  // Handle speaker click from transcript
  const handleSpeakerClick = useCallback((segment: TranscriptSegment) => {
    setSelectedSegment(segment);
    setShowTagSheet(true);
  }, []);

  // Handle segment updates from transcript editing
  const handleSegmentsUpdate = useCallback(
    (segmentIds: string[], personId: string | null, isUser: boolean) => {
      if (!conversation || !onConversationUpdate) return;

      const updatedSegments = (conversation.transcript_segments ?? []).map((seg) => {
        if (seg.id && segmentIds.includes(seg.id)) {
          return {
            ...seg,
            is_user: isUser,
            person_id: isUser ? null : personId,
          };
        }
        return seg;
      });

      onConversationUpdate({
        ...conversation,
        transcript_segments: updatedSegments,
      });
    },
    [conversation, onConversationUpdate],
  );

  // Immutably patch a single segment's text from the *latest* conversation state
  // (via ref, not a stale closure) so overlapping edits don't drop each other.
  const applyOptimisticText = useCallback(
    (segmentId: string, text: string) => {
      const latest = conversationRef.current;
      if (!latest || !onConversationUpdate) return;
      onConversationUpdate({
        ...latest,
        transcript_segments: (latest.transcript_segments ?? []).map((seg) =>
          seg.id === segmentId ? { ...seg, text } : seg,
        ),
      });
    },
    [onConversationUpdate],
  );

  // Drain the save queue one PATCH at a time. Serializing is the correctness fix:
  // the backend rewrites the whole segments array, so concurrent writes lose-update
  // — running them sequentially means each save reads the previous one's result.
  const processSaveQueue = useCallback(async () => {
    if (processingRef.current) return;
    processingRef.current = true;
    const convId = convIdRef.current;
    try {
      while (saveQueueRef.current.length > 0) {
        // Abandon the batch if the user navigated to another conversation.
        if (convIdRef.current !== convId) {
          saveQueueRef.current = [];
          break;
        }
        const task = saveQueueRef.current.shift()!;
        setSaveBatch((s) => ({ ...s, savingId: task.segmentId }));
        try {
          await updateSegmentText(convId, task.segmentId, task.text);
          if (convIdRef.current === convId) {
            setTranscriptEdited(true);
            MixpanelManager.track('Transcript Segment Edited', {
              conversation_id: convId,
              segment_id: task.segmentId,
            });
          }
        } catch (error) {
          console.error('Failed to save transcript segment edit:', error);
          // Revert the optimistic change so the UI reflects the persisted truth.
          if (convIdRef.current === convId)
            applyOptimisticText(task.segmentId, task.prevText);
          setSaveBatch((s) => ({ ...s, failed: s.failed + 1 }));
        } finally {
          setSaveBatch((s) => ({ ...s, done: s.done + 1, savingId: null }));
        }
      }
    } finally {
      processingRef.current = false;
      // Collapse the progress counters once the queue is fully drained (keep the
      // failure count so the error banner persists until the next edit).
      if (saveQueueRef.current.length === 0) {
        setSaveBatch((s) => ({ total: 0, done: 0, savingId: null, failed: s.failed }));
      }
    }
  }, [applyOptimisticText]);

  // Enqueue a segment edit: show it optimistically now, persist it in order.
  const enqueueSegmentSave = useCallback(
    (segmentId: string, text: string) => {
      const latest = conversationRef.current;
      if (!latest) return;
      const prevText =
        (latest.transcript_segments ?? []).find((seg) => seg.id === segmentId)?.text ??
        '';
      const trimmed = text.trim();
      if (!trimmed || trimmed === prevText) return;

      applyOptimisticText(segmentId, trimmed);
      saveQueueRef.current.push({ segmentId, text: trimmed, prevText });
      // A new edit while the queue is idle starts a fresh batch (clears old errors).
      setSaveBatch((s) => {
        const fresh = s.total === s.done;
        return {
          total: (fresh ? 0 : s.total) + 1,
          done: fresh ? 0 : s.done,
          savingId: s.savingId,
          failed: fresh ? 0 : s.failed,
        };
      });
      void processSaveQueue();
    },
    [applyOptimisticText, processSaveQueue],
  );

  // Reprocess the conversation to refresh summary/search after transcript edits.
  // Reprocessing is heavy; race it against a timeout so a hung request can't leave
  // the UI stuck on "Reprocessing…", and surface failures to the user (not console).
  const handleReprocessAfterEdit = useCallback(async () => {
    const convId = convIdRef.current;
    setIsReprocessing(true);
    setReprocessFailed(false);
    try {
      const updated = await Promise.race([
        reprocessConversation(convId),
        new Promise<never>((_, reject) =>
          setTimeout(
            () => reject(new Error('Reprocess timed out')),
            REPROCESS_TIMEOUT_MS,
          ),
        ),
      ]);
      // Ignore the response if the user has since switched conversations.
      if (convIdRef.current === convId) {
        onConversationUpdate?.(updated);
        setTranscriptEdited(false);
        MixpanelManager.track('Conversation Reprocessed After Edit', {
          conversation_id: convId,
        });
      }
    } catch (error) {
      console.error('Failed to reprocess conversation after edit:', error);
      if (convIdRef.current === convId) setReprocessFailed(true);
    } finally {
      if (convIdRef.current === convId) setIsReprocessing(false);
    }
  }, [onConversationUpdate]);

  // Handle title change - update conversation with new title
  const handleTitleChange = useCallback(
    (newTitle: string) => {
      if (conversation && onConversationUpdate) {
        onConversationUpdate({
          ...conversation,
          structured: {
            ...conversation.structured,
            title: newTitle,
          },
        });
      }
    },
    [conversation, onConversationUpdate],
  );

  // Handle delete
  const handleDelete = useCallback(() => {
    if (onDelete) {
      onDelete();
    } else if (onBack) {
      onBack();
    }
  }, [onDelete, onBack]);

  if (loading || !conversation) {
    return <DetailSkeleton />;
  }

  const { structured, transcript_segments, geolocation } = conversation;
  const duration = conversationDurationSeconds(conversation.started_at, conversation.finished_at);
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
  ];

  // Filter to only enabled tabs
  const enabledTabs = tabs.filter((tab) => !tab.disabled);

  // Ensure active tab is valid
  if (!enabledTabs.find((t) => t.id === activeTab)) {
    const firstEnabled = enabledTabs[0];
    if (firstEnabled && activeTab !== firstEnabled.id) {
      setActiveTab(firstEnabled.id);
    }
  }

  return (
    <div className="h-full flex flex-col overflow-hidden relative">
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
            {/* Editable Title */}
            <EditableTitle
              conversationId={conversationId}
              title={structured.title || 'Untitled Conversation'}
              onTitleChange={handleTitleChange}
              className="text-xl font-display font-semibold text-text-primary mb-2 line-clamp-2"
            />

            {/* Meta info */}
            <div className="flex flex-wrap items-center gap-3 text-sm text-text-tertiary">
              {conversation.started_at && (
                <div className="flex items-center gap-1.5">
                  <Calendar className="w-4 h-4" />
                  <span>{formatConversationDate(conversation.started_at)}</span>
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

          {/* Actions Menu */}
          <ConversationActionsMenu
            conversation={conversation}
            people={people}
            onConversationUpdate={onConversationUpdate}
            onDelete={handleDelete}
          />
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
                    ? 'bg-text-primary text-bg-primary'
                    : 'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary',
                )}
              >
                {tab.icon}
                <span>{tab.label}</span>
                {tab.count !== undefined && tab.count > 0 && (
                  <span
                    className={cn(
                      'px-1.5 py-0.5 rounded-full text-xs',
                      activeTab === tab.id ? 'bg-white/20' : 'bg-bg-tertiary',
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
                geolocation={geolocation}
              />
            )}

            {activeTab === 'actions' && hasActionItems && (
              <ActionItemsTab items={actionItems} />
            )}

            {activeTab === 'transcript' && hasTranscript && (
              <div className="space-y-4">
                {/* Audio Player - only show when we have signed URLs ready */}
                {fetchedAudioFiles.length > 0 && fetchedAudioFiles[0].signed_url && (
                  <AudioPlayer
                    ref={audioPlayerRef}
                    conversationId={conversationId}
                    audioFiles={fetchedAudioFiles}
                    onTimeUpdate={handleAudioTimeUpdate}
                    className="sticky top-0 z-10"
                  />
                )}
                {/* Loading state while fetching signed URLs */}
                {audioAvailable && fetchedAudioFiles.length === 0 && (
                  <div className="flex items-center gap-3 p-3 rounded-xl bg-bg-tertiary border border-bg-quaternary/50 text-text-tertiary text-sm">
                    <div className="w-10 h-10 rounded-full flex items-center justify-center bg-text-primary/90">
                      <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    </div>
                    <span>Loading audio...</span>
                  </div>
                )}
                {/* Save-queue progress: edits persist one at a time (serialized) */}
                {isSavingSegments && (
                  <div className="flex items-center gap-3 p-3 rounded-xl bg-bg-tertiary border border-bg-quaternary/50 text-sm text-text-secondary">
                    <div className="w-4 h-4 border-2 border-text-quaternary border-t-transparent rounded-full animate-spin flex-shrink-0" />
                    <span>
                      Saving edit {Math.min(saveBatch.done + 1, saveBatch.total)} of{' '}
                      {saveBatch.total}…
                    </span>
                  </div>
                )}
                {/* Failed-save banner (edits were reverted to their saved value) */}
                {!isSavingSegments && saveBatch.failed > 0 && (
                  <div className="flex items-center gap-2 p-3 rounded-xl bg-error/10 border border-error/20 text-sm text-error">
                    <span>
                      Couldn&apos;t save {saveBatch.failed} edit
                      {saveBatch.failed > 1 ? 's' : ''} — reverted to the saved text.
                      Please try again.
                    </span>
                  </div>
                )}
                {/* Reprocess failed/timed out — surface it and let the user retry */}
                {reprocessFailed && !isReprocessing && !conversation.discarded && (
                  <div className="flex items-center justify-between gap-3 p-3 rounded-xl bg-error/10 border border-error/20">
                    <span className="text-sm text-error">
                      Reprocessing failed — the summary and search may be out of date.
                    </span>
                    <button
                      onClick={handleReprocessAfterEdit}
                      className={cn(
                        'flex items-center gap-1.5 flex-shrink-0 px-3 py-1.5 rounded-lg text-sm font-medium',
                        'bg-white text-bg-primary hover:bg-white/90 transition-colors',
                      )}
                    >
                      <RefreshCw className="w-3.5 h-3.5" />
                      <span>Retry</span>
                    </button>
                  </div>
                )}
                {/* Nudge to refresh derived summary/search after edits (once saved) */}
                {transcriptEdited &&
                  !conversation.discarded &&
                  !isSavingSegments &&
                  saveBatch.failed === 0 &&
                  !reprocessFailed && (
                    <div className="flex items-center justify-between gap-3 p-3 rounded-xl bg-bg-tertiary border border-bg-quaternary/50">
                      <div className="flex items-center gap-2 text-sm text-text-secondary">
                        <Sparkles className="w-4 h-4 text-text-secondary flex-shrink-0" />
                        <span>
                          Transcript edited. Reprocess to update the summary and search.
                        </span>
                      </div>
                      <button
                        onClick={handleReprocessAfterEdit}
                        disabled={isReprocessing}
                        className={cn(
                          'flex items-center gap-1.5 flex-shrink-0 px-3 py-1.5 rounded-lg text-sm font-medium',
                          'bg-white text-bg-primary hover:bg-white/90 transition-colors',
                          'disabled:opacity-60',
                        )}
                      >
                        <RefreshCw
                          className={cn('w-3.5 h-3.5', isReprocessing && 'animate-spin')}
                        />
                        <span>{isReprocessing ? 'Reprocessing…' : 'Reprocess'}</span>
                      </button>
                    </div>
                  )}
                <TranscriptView
                  segments={transcript_segments}
                  userName={userName}
                  conversationId={conversationId}
                  people={people}
                  editable={true}
                  onSpeakerClick={handleSpeakerClick}
                  onSegmentTextChange={enqueueSegmentSave}
                  savingSegmentId={saveBatch.savingId}
                  editingDisabled={isReprocessing}
                  currentTime={currentPlaybackTime}
                  hasAudio={audioAvailable}
                  onSeekTo={handleSeekTo}
                />
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Speaker Tag Sheet - positioned at panel level for proper anchoring */}
      {selectedSegment && (
        <SpeakerTagSheet
          isOpen={showTagSheet}
          onClose={() => {
            setShowTagSheet(false);
            setSelectedSegment(null);
          }}
          conversationId={conversationId}
          segment={selectedSegment}
          allSegments={transcript_segments || []}
          onAssignComplete={handleSegmentsUpdate}
          onManagePeople={() => {
            setShowTagSheet(false);
            setShowManagePeople(true);
          }}
        />
      )}

      {/* Manage People Modal */}
      <ManagePeopleModal
        isOpen={showManagePeople}
        onClose={() => {
          setShowManagePeople(false);
          // Reopen tag sheet if we have a selected segment
          if (selectedSegment) {
            setShowTagSheet(true);
          }
        }}
      />
    </div>
  );
}
