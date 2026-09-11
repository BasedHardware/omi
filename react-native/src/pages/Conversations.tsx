import React, {memo, useEffect, useMemo, useRef, useState} from 'react';
import {
  ActivityIndicator,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  useWindowDimensions,
} from 'react-native';
import Search from 'lucide-react-native/icons/search';
import {
  conversationCaptureCopy,
  conversationPhotoCountCopy,
  conversationDisplaySummary,
  conversationDisplayTitle,
  conversationHasFinishClock,
  conversationListEmoji,
  conversationListNewCopy,
  conversationListStatusCopy,
  conversationListTag,
  conversationListUsesListenOverview,
  conversationRecapTitle,
  conversationDayLabel,
  conversationGroupLabel,
  desktopBackendUnavailableCopy,
  formatConversationDuration,
  visibleDisplayText,
  type ConversationProjection,
  type DesktopReadProjection,
  type DomainReadOutcome,
  type TaskCardLookup,
} from '../desktopReadClient';
import {FocusPressable} from '../ui/Pressable';
import {
  ConversationDetail,
  formatConversationDate,
} from '../ui/ConversationDetail';
import {ReadStatus, emptyLibraryCopy} from '../ui/ReadStatus';
import {styles} from '../ui/styles';
import {goalProgressCopy, loadOmiGoals, type OmiGoal} from '../legacyOmiGoals';
import {loadOmiFolderNames, type OmiFolder} from '../legacyOmiFolders';
import {
  calendarCaptureGapSpan,
  captureGapHeaderCopy,
  captureGapTimeRangeCopy,
  loadOmiCalendarCaptureGaps,
  type OmiCalendarCaptureGap,
} from '../legacyOmiCalendarCaptureGaps';
import type {OmiBackend} from '../omiNativeTypes';

function conversationLocalDay(value: string): number | null {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp) || timestamp <= 0) {
    return null;
  }
  const date = new Date(timestamp);
  return new Date(
    date.getFullYear(),
    date.getMonth(),
    date.getDate(),
  ).getTime();
}

const ConversationRow = memo(function ConversationRow({
  item,
  selected,
  onPress,
}: {
  item: ConversationProjection;
  selected: boolean;
  onPress: () => void;
}) {
  const listenOverview = conversationListUsesListenOverview(item);
  const captureCopy = conversationCaptureCopy(item.capturedAtMs);
  const emoji = conversationListEmoji(item);
  const photosCopy = conversationPhotoCountCopy(item);
  const tag = conversationListTag(item);
  const listStatusCopy = conversationListStatusCopy(item.status);
  const newCopy = conversationListNewCopy(
    item.createdAt,
    item.finishedAt,
    Date.now(),
  );
  return (
    <FocusPressable
      accessibilityLabel={`Open conversation ${conversationRecapTitle(item)}`}
      accessibilityRole="button"
      accessibilityState={{selected}}
      onPress={onPress}
      style={({pressed}) => [
        styles.conversationRow,
        selected && styles.conversationRowSelected,
        pressed && styles.pressed,
      ]}>
      <View style={styles.conversationRowMeta}>
        <Text style={styles.conversationRowTime}>
          {newCopy ?? formatConversationDate(item.startedAt ?? item.createdAt)}
        </Text>
        {captureCopy !== null ? (
          <Text style={styles.conversationRowTime}>{captureCopy}</Text>
        ) : null}
        {item.starred ? (
          <Text
            accessibilityLabel="Starred conversation"
            style={styles.conversationRowStar}>
            ★
          </Text>
        ) : null}
        {item.locked ? (
          <Text
            accessibilityLabel="Locked conversation"
            style={styles.conversationRowTime}>
            Locked
          </Text>
        ) : null}
        {item.discarded ? (
          <Text
            accessibilityLabel="Discarded conversation"
            style={styles.conversationRowTime}>
            Discarded
          </Text>
        ) : null}
        {photosCopy !== null ? (
          <Text
            accessibilityLabel={photosCopy}
            style={styles.conversationRowTime}>
            {photosCopy}
          </Text>
        ) : null}
        {listStatusCopy !== null ? (
          <Text
            accessibilityLabel={`${listStatusCopy} conversation`}
            style={styles.conversationRowTime}>
            {listStatusCopy}
          </Text>
        ) : null}
      </View>
      {emoji !== null ? (
        <Text
          accessibilityLabel="Conversation emoji"
          style={styles.conversationRowStar}>
          {emoji}
        </Text>
      ) : null}
      {tag !== null ? (
        <Text style={styles.conversationRowTime}>{tag}</Text>
      ) : null}
      <Text numberOfLines={listenOverview ? 3 : 1} style={styles.resultTitle}>
        {listenOverview
          ? conversationRecapTitle(item)
          : conversationDisplayTitle(item)}
      </Text>
      {listenOverview ? null : (
        <Text numberOfLines={2} style={styles.resultSummary}>
          {conversationDisplaySummary(item)}
        </Text>
      )}
      {conversationHasFinishClock(item) ? (
        <Text style={styles.conversationRowDuration}>
          {formatConversationDuration(item.startedAt, item.finishedAt)}
        </Text>
      ) : null}
    </FocusPressable>
  );
});

export function ConversationsPage({
  outcome,
  loading,
  embedded = false,
  onRefresh,
  onLoadMore,
  loadingMore = false,
  notice = null,
  requestedConversationId = null,
  onRequestedConversationConsumed,
  backend = null,
  tasks = [],
}: {
  outcome: DomainReadOutcome<DesktopReadProjection> | null;
  loading: boolean;
  embedded?: boolean;
  onRefresh?: () => void;
  onLoadMore?: () => void;
  loadingMore?: boolean;
  notice?: string | null;
  requestedConversationId?: string | null;
  onRequestedConversationConsumed?: () => void;
  backend?: OmiBackend | null;
  tasks?: readonly TaskCardLookup[];
}) {
  const compact = useWindowDimensions().width < 720;
  const conversations = useMemo(
    () =>
      outcome?.status === 'success'
        ? outcome.value.items.filter(
            (item): item is ConversationProjection =>
              item.kind === 'conversation',
          )
        : [],
    [outcome],
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [starredOnly, setStarredOnly] = useState(false);
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null);
  const nowEpochMilliseconds = useRef(Date.now()).current;
  const selected = conversations.find(item => item.id === selectedId) ?? null;
  useEffect(() => {
    if (requestedConversationId === null) {
      return;
    }
    setSelectedId(requestedConversationId);
    onRequestedConversationConsumed?.();
  }, [onRequestedConversationConsumed, requestedConversationId]);
  const error = outcome?.status === 'error' ? outcome.error : null;
  const filtered = useMemo(() => {
    const normalized = visibleDisplayText(query).toLocaleLowerCase();
    return conversations.filter(
      item =>
        (selectedFolderId === null || item.folderId === selectedFolderId) &&
        (!starredOnly || item.starred) &&
        (normalized === '' ||
          item.title.toLocaleLowerCase().includes(normalized) ||
          conversationDisplayTitle(item)
            .toLocaleLowerCase()
            .includes(normalized) ||
          conversationDisplaySummary(item)
            .toLocaleLowerCase()
            .includes(normalized) ||
          item.summary.toLocaleLowerCase().includes(normalized)),
    );
  }, [conversations, query, selectedFolderId, starredOnly]);
  useEffect(() => {
    if (selectedId !== null && !filtered.some(item => item.id === selectedId)) {
      setSelectedId(null);
    }
  }, [filtered, selectedId]);
  const searching = visibleDisplayText(query) !== '';
  const filtering = searching || starredOnly || selectedFolderId !== null;
  const [goals, setGoals] = useState<OmiGoal[]>([]);
  const [folders, setFolders] = useState<OmiFolder[]>([]);
  const [captureGaps, setCaptureGaps] = useState<OmiCalendarCaptureGap[]>([]);
  const grouped = useMemo(() => {
    const groups: Array<{
      label: string;
      day: number;
      items: ConversationProjection[];
      gaps: OmiCalendarCaptureGap[];
    }> = [];
    const byDay = new Map<
      number,
      {
        label: string;
        day: number;
        items: ConversationProjection[];
        gaps: OmiCalendarCaptureGap[];
      }
    >();
    for (const item of filtered) {
      const label = conversationDayLabel(
        item.startedAt,
        item.createdAt,
        nowEpochMilliseconds,
      );
      const day =
        conversationLocalDay(item.startedAt ?? item.createdAt) ??
        Number.NEGATIVE_INFINITY;
      let group = byDay.get(day);
      if (group === undefined) {
        group = {label, day, items: [], gaps: []};
        byDay.set(day, group);
        groups.push(group);
      }
      group.items.push(item);
    }
    if (!filtering) {
      for (const gap of captureGaps) {
        const iso = new Date(gap.startMs).toISOString();
        const day = conversationLocalDay(iso);
        if (day === null) {
          continue;
        }
        let group = byDay.get(day);
        if (group === undefined) {
          group = {
            label: conversationGroupLabel(iso, nowEpochMilliseconds),
            day,
            items: [],
            gaps: [],
          };
          byDay.set(day, group);
          const index = groups.findIndex(existing => existing.day < day);
          if (index === -1) {
            groups.push(group);
          } else {
            groups.splice(index, 0, group);
          }
        }
        group.gaps.push(gap);
      }
    }
    return groups;
  }, [captureGaps, filtered, filtering, nowEpochMilliseconds]);
  useEffect(() => {
    if (backend === undefined || backend === null) {
      setGoals([]);
      return;
    }
    let cancelled = false;
    loadOmiGoals(backend)
      .then(rows => {
        if (!cancelled) {
          setGoals(rows);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setGoals([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [backend, loading]);
  useEffect(() => {
    if (backend === undefined || backend === null) {
      setFolders([]);
      return;
    }
    let cancelled = false;
    loadOmiFolderNames(backend)
      .then(rows => {
        if (!cancelled) {
          setFolders(rows);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setFolders([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [backend, loading]);
  useEffect(() => {
    if (
      selectedFolderId !== null &&
      !folders.some(folder => folder.id === selectedFolderId)
    ) {
      setSelectedFolderId(null);
    }
  }, [folders, selectedFolderId]);
  const captureGapWindow = useMemo(
    () => calendarCaptureGapSpan(conversations),
    [conversations],
  );
  useEffect(() => {
    if (
      backend === undefined ||
      backend === null ||
      captureGapWindow === null
    ) {
      setCaptureGaps([]);
      return;
    }
    let cancelled = false;
    loadOmiCalendarCaptureGaps(backend, captureGapWindow)
      .then(rows => {
        if (!cancelled) {
          setCaptureGaps(rows);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCaptureGaps([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [backend, captureGapWindow, loading]);

  return (
    <View
      style={[
        styles.conversationPage,
        compact && mobileStyles.page,
        embedded && mobileStyles.embedded,
      ]}>
      {!embedded && (
        <Text
          style={[
            styles.projectionTitle,
            Platform.OS === 'macos' && styles.macPrimaryText,
          ]}>
          Conversations
        </Text>
      )}
      {(!compact || selected === null) && (
        <View style={embedded ? mobileStyles.discovery : undefined}>
          <View style={styles.conversationDiscovery}>
            <View style={styles.conversationSearchBox}>
              <Search accessible={false} color="#777777" size={17} />
              <TextInput
                accessibilityLabel="Search loaded conversations"
                onChangeText={setQuery}
                placeholder="Search loaded conversations"
                placeholderTextColor="#666666"
                style={styles.memorySearchInput}
                value={query}
              />
            </View>
            <FocusPressable
              accessibilityLabel="Show starred conversations"
              accessibilityRole="button"
              accessibilityState={{selected: starredOnly}}
              onPress={() => setStarredOnly(value => !value)}
              style={({pressed}) => [
                styles.conversationStarFilter,
                starredOnly && styles.conversationStarFilterActive,
                pressed && styles.pressed,
              ]}>
              <Text
                style={[
                  styles.conversationStarFilterText,
                  starredOnly && styles.conversationStarFilterTextActive,
                ]}>
                Starred
              </Text>
            </FocusPressable>
          </View>
          {folders.length > 0 ? (
            <View style={styles.conversationFolderFilters}>
              {folders.map(folder => {
                const selectedFolder = selectedFolderId === folder.id;
                return (
                  <FocusPressable
                    accessibilityLabel={`Show ${folder.name} conversations`}
                    accessibilityRole="button"
                    accessibilityState={{selected: selectedFolder}}
                    key={folder.id}
                    onPress={() =>
                      setSelectedFolderId(current =>
                        current === folder.id ? null : folder.id,
                      )
                    }
                    style={({pressed}) => [
                      styles.conversationStarFilter,
                      selectedFolder && styles.conversationStarFilterActive,
                      pressed && styles.pressed,
                    ]}>
                    <Text
                      numberOfLines={1}
                      style={[
                        styles.conversationStarFilterText,
                        selectedFolder &&
                          styles.conversationStarFilterTextActive,
                      ]}>
                      {folder.name}
                    </Text>
                  </FocusPressable>
                );
              })}
            </View>
          ) : null}
        </View>
      )}
      <View style={styles.conversationContent}>
        {(!compact || selected === null) && (
          <ScrollView
            contentContainerStyle={styles.conversationList}
            style={styles.conversationListPane}>
            {onRefresh && error !== desktopBackendUnavailableCopy && (
              <FocusPressable
                accessibilityRole="button"
                accessibilityLabel="Refresh conversations"
                disabled={loading || loadingMore}
                onPress={onRefresh}
                style={mobileStyles.pageAction}>
                <Text style={styles.projectionEmptyCopy}>
                  {loading ? 'Refreshing…' : 'Refresh'}
                </Text>
              </FocusPressable>
            )}
            {notice && (
              <Text
                accessibilityRole="alert"
                style={styles.projectionEmptyCopy}>
                {notice}
              </Text>
            )}
            {goals.length > 0 && !searching && !starredOnly ? (
              <View>
                <Text style={styles.projectionEmptyTitle}>Goals</Text>
                {goals.map(goal => (
                  <View key={goal.id}>
                    <Text numberOfLines={1} style={styles.resultTitle}>
                      {goal.title}
                    </Text>
                    <Text style={styles.conversationRowTime}>
                      {goalProgressCopy(goal.current, goal.target)}
                    </Text>
                  </View>
                ))}
              </View>
            ) : null}
            {loading && outcome === null ? (
              <View style={styles.projectionEmpty}>
                <ActivityIndicator color="#888888" />
                <Text style={styles.projectionEmptyCopy}>
                  Loading conversations…
                </Text>
              </View>
            ) : error !== null ? (
              <View style={styles.projectionEmpty}>
                <Text style={styles.projectionEmptyTitle}>
                  Conversations unavailable
                </Text>
                <Text style={styles.projectionEmptyCopy}>{error}</Text>
              </View>
            ) : grouped.length === 0 ? (
              <View style={styles.projectionEmpty}>
                <Text style={styles.projectionEmptyTitle}>
                  {emptyLibraryCopy(
                    'Conversations',
                    outcome?.status === 'success' ? outcome.value.page : null,
                    filtering,
                    'No loaded conversations match.',
                    'No conversations yet.',
                    notice === desktopBackendUnavailableCopy,
                  )}
                </Text>
                {filtering && (
                  <Text style={styles.projectionEmptyCopy}>
                    Search and filters cover conversations already loaded on
                    this device.
                  </Text>
                )}
              </View>
            ) : (
              grouped.map(group => {
                const gapHeader = captureGapHeaderCopy(group.gaps.length);
                return (
                  <View key={group.label} style={styles.conversationGroup}>
                    <Text style={styles.conversationGroupTitle}>
                      {group.label}
                    </Text>
                    {gapHeader !== '' ? (
                      <Text style={styles.conversationRowTime}>
                        {gapHeader}
                      </Text>
                    ) : null}
                    {group.gaps.map(gap => {
                      const timeCopy = captureGapTimeRangeCopy(
                        gap.startMs,
                        gap.endMs,
                      );
                      return (
                        <View key={gap.eventId}>
                          <Text numberOfLines={1} style={styles.resultTitle}>
                            {gap.title}
                          </Text>
                          {timeCopy !== '' ? (
                            <Text style={styles.conversationRowTime}>
                              {timeCopy}
                            </Text>
                          ) : null}
                        </View>
                      );
                    })}
                    {group.items.map(item => (
                      <ConversationRow
                        item={item}
                        key={item.id}
                        onPress={() => setSelectedId(item.id)}
                        selected={selectedId === item.id}
                      />
                    ))}
                  </View>
                );
              })
            )}
            {outcome?.status === 'success' &&
              outcome.value.page.hasMore &&
              onLoadMore && (
                <FocusPressable
                  accessibilityRole="button"
                  accessibilityLabel="Load more conversations"
                  disabled={loading || loadingMore}
                  onPress={onLoadMore}
                  style={mobileStyles.pageAction}>
                  <Text style={styles.projectionEmptyCopy}>
                    {loadingMore ? 'Loading…' : 'Load more conversations'}
                  </Text>
                </FocusPressable>
              )}
            {outcome?.status === 'success' &&
              (grouped.length > 0 || filtering) && (
                <ReadStatus
                  continueUnavailable={notice === desktopBackendUnavailableCopy}
                  label="Conversations"
                  page={outcome.value.page}
                />
              )}
          </ScrollView>
        )}
        {(!compact || selected !== null) && (
          <ScrollView
            accessibilityLabel="Selected conversation details"
            contentContainerStyle={styles.conversationDetailContent}
            style={styles.conversationDetail}>
            {selected === null ? (
              <View style={styles.conversationDetailEmpty}>
                <Text style={styles.projectionEmptyTitle}>
                  Select a conversation
                </Text>
                <Text style={styles.projectionEmptyCopy}>
                  Choose a conversation to view its summary and details.
                </Text>
              </View>
            ) : (
              <>
                {compact && (
                  <FocusPressable
                    accessibilityRole="button"
                    accessibilityLabel="Back to conversations"
                    onPress={() => setSelectedId(null)}
                    style={styles.conversationTranscriptAction}>
                    <Text style={styles.conversationDetailField}>
                      Back to conversations
                    </Text>
                  </FocusPressable>
                )}
                <ConversationDetail
                  apiContract={
                    outcome?.status === 'success'
                      ? outcome.value.apiContract
                      : undefined
                  }
                  conversation={selected}
                  tasks={tasks}
                />
              </>
            )}
          </ScrollView>
        )}
      </View>
    </View>
  );
}

const mobileStyles = StyleSheet.create({
  pageAction: {minHeight: 44, justifyContent: 'center'},
  page: {paddingHorizontal: 20, paddingVertical: 16},
  embedded: {paddingTop: 0, paddingBottom: 0},
  discovery: {marginTop: 0},
});
