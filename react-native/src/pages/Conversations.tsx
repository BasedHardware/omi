import React, {memo, useEffect, useMemo, useRef, useState} from 'react';
import {
  ActivityIndicator,
  AppState,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  useWindowDimensions,
} from 'react-native';
import Search from 'lucide-react-native/icons/search';
import X from 'lucide-react-native/icons/x';
import ChevronLeft from 'lucide-react-native/icons/chevron-left';
import {
  conversationGroupLabel,
  type ConversationProjection,
  type DesktopReadProjection,
  type DomainReadOutcome,
} from '../desktopReadClient';
import {FocusPressable} from '../ui/Pressable';
import {
  ConversationDetail,
  formatConversationDate,
  formatConversationDuration,
} from '../ui/ConversationDetail';
import {ReadStatus} from '../ui/ReadStatus';
import {matchesSearchQuery} from '../searchText';
import {styles} from '../ui/styles';
import {mobileColor} from '../mobile/mobileTokens';
import {OmiAvatar} from '../ui/OmiAvatar';
import {useReduceMotion} from '../app/useReduceMotion';

const ConversationRow = memo(function ConversationRow({
  item,
  selected,
  onPress,
  embedded,
}: {
  item: ConversationProjection;
  selected: boolean;
  onPress: () => void;
  embedded: boolean;
}) {
  return (
    <FocusPressable
      accessibilityLabel={`Open conversation ${item.title}`}
      accessibilityRole="button"
      accessibilityState={{selected}}
      onPress={onPress}
      style={({pressed}) => [
        styles.conversationRow,
        embedded && mobileStyles.card,
        selected && styles.conversationRowSelected,
        pressed && styles.pressed,
      ]}>
      <View style={styles.conversationRowMeta}>
        <Text
          style={[styles.conversationRowTime, embedded && mobileStyles.meta]}>
          {formatConversationDate(item.startedAt ?? item.createdAt)}
        </Text>
        <Text
          accessibilityLabel={
            item.starred ? 'Starred conversation' : 'Not starred'
          }
          style={styles.conversationRowStar}>
          {item.starred ? '★' : '☆'}
        </Text>
      </View>
      <Text
        numberOfLines={2}
        style={[styles.resultTitle, embedded && mobileStyles.title]}>
        {item.title}
      </Text>
      <Text
        numberOfLines={2}
        style={[styles.resultSummary, embedded && mobileStyles.summary]}>
        {item.summary}
      </Text>
      <Text
        style={[styles.conversationRowDuration, embedded && mobileStyles.meta]}>
        {formatConversationDuration(item.startedAt, item.finishedAt)}
      </Text>
    </FocusPressable>
  );
});

export function ConversationsPage({
  search,
  outcome,
  loading,
  embedded = false,
  onRefresh,
  onLoadMore,
  loadingMore = false,
  preserveLoadedPages = false,
  notice = null,
}: {
  search?: {value: string; onChange: (value: string) => void};
  outcome: DomainReadOutcome<DesktopReadProjection> | null;
  loading: boolean;
  embedded?: boolean;
  onRefresh?: () => void;
  onLoadMore?: () => void;
  loadingMore?: boolean;
  preserveLoadedPages?: boolean;
  notice?: string | null;
}) {
  const compact = useWindowDimensions().width < 720;
  const reduceMotion = useReduceMotion();
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
  const [localQuery, setLocalQuery] = useState('');
  const query = search?.value ?? localQuery;
  const setQuery = search?.onChange ?? setLocalQuery;
  const [starredOnly, setStarredOnly] = useState(false);
  const nowEpochMilliseconds = useRef(Date.now()).current;
  const selected = conversations.find(item => item.id === selectedId) ?? null;
  const scrolledAway = useRef(false);
  const paginated = useRef(preserveLoadedPages);
  paginated.current = preserveLoadedPages || paginated.current;
  const refreshState = useRef({onRefresh, loading, loadingMore, selectedId});
  refreshState.current = {onRefresh, loading, loadingMore, selectedId};
  const refreshEnabled = onRefresh !== undefined;

  useEffect(() => {
    if (!refreshEnabled) return;
    let active =
      AppState.currentState !== 'background' &&
      AppState.currentState !== 'inactive';
    const refresh = () => {
      const current = refreshState.current;
      if (
        active &&
        !current.loading &&
        !current.loadingMore &&
        current.selectedId === null &&
        !scrolledAway.current &&
        !paginated.current
      ) {
        current.onRefresh?.();
      }
    };
    const listener = AppState.addEventListener('change', state => {
      active = state === 'active';
      if (active) refresh();
    });
    refresh();
    const timer = setInterval(refresh, 15000);
    return () => {
      clearInterval(timer);
      listener.remove();
    };
  }, [refreshEnabled]);

  const error = outcome?.status === 'error' ? outcome.error : null;
  const filtered = useMemo(() => {
    return conversations.filter(
      item =>
        (!starredOnly || item.starred) &&
        (matchesSearchQuery(item.title, query) ||
          matchesSearchQuery(item.summary, query)),
    );
  }, [conversations, query, starredOnly]);
  useEffect(() => {
    if (selectedId !== null && !filtered.some(item => item.id === selectedId)) {
      setSelectedId(null);
    }
  }, [filtered, selectedId]);
  const grouped = useMemo(
    () =>
      filtered.reduce<Array<{label: string; items: ConversationProjection[]}>>(
        (groups, item) => {
          const label = conversationGroupLabel(
            item.startedAt ?? item.createdAt,
            nowEpochMilliseconds,
          );
          const current = groups.find(group => group.label === label);
          if (current !== undefined) {
            current.items.push(item);
          } else {
            groups.push({label, items: [item]});
          }
          return groups;
        },
        [],
      ),
    [filtered, nowEpochMilliseconds],
  );
  const filtering = query.trim() !== '' || starredOnly;

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
        <View
          style={[
            styles.conversationDiscovery,
            embedded && mobileStyles.discovery,
          ]}>
          {!search && (
            <View
              style={[
                styles.conversationSearchBox,
                embedded && mobileStyles.search,
              ]}>
              <Search accessible={false} color="#777777" size={17} />
              <TextInput
                accessibilityLabel="Search loaded conversations"
                onChangeText={setQuery}
                placeholder={
                  embedded
                    ? 'Search loaded conversations…'
                    : 'Search loaded conversations'
                }
                placeholderTextColor={
                  embedded ? mobileColor.textSubtle : '#666666'
                }
                style={[
                  styles.memorySearchInput,
                  embedded && mobileStyles.searchInput,
                ]}
                value={query}
              />
              {embedded && query.length > 0 && (
                <FocusPressable
                  accessibilityRole="button"
                  accessibilityLabel="Clear conversation search"
                  onPress={() => setQuery('')}
                  style={mobileStyles.clear}>
                  <X size={18} color={mobileColor.textMuted} />
                </FocusPressable>
              )}
            </View>
          )}
          <View style={embedded && mobileStyles.filters}>
            {embedded && (
              <FocusPressable
                accessibilityRole="button"
                accessibilityLabel="Show all conversations"
                accessibilityState={{selected: !starredOnly}}
                onPress={() => setStarredOnly(false)}
                style={[
                  mobileStyles.filter,
                  !starredOnly && mobileStyles.filterSelected,
                ]}>
                <Text
                  style={[
                    mobileStyles.filterText,
                    !starredOnly && mobileStyles.filterTextSelected,
                  ]}>
                  All
                </Text>
              </FocusPressable>
            )}
            <FocusPressable
              accessibilityLabel="Show starred conversations"
              accessibilityRole="button"
              accessibilityState={{selected: starredOnly}}
              onPress={() => setStarredOnly(value => embedded || !value)}
              style={({pressed}) => [
                styles.conversationStarFilter,
                starredOnly && styles.conversationStarFilterActive,
                embedded && mobileStyles.filter,
                embedded && starredOnly && mobileStyles.filterSelected,
                pressed && styles.pressed,
              ]}>
              <Text
                style={[
                  styles.conversationStarFilterText,
                  starredOnly && styles.conversationStarFilterTextActive,
                  embedded && mobileStyles.filterText,
                  embedded && starredOnly && mobileStyles.filterTextSelected,
                ]}>
                Starred
              </Text>
            </FocusPressable>
          </View>
        </View>
      )}
      <View
        style={[styles.conversationContent, compact && mobileStyles.content]}>
        {(!compact || selected === null) && (
          <ScrollView
            keyboardShouldPersistTaps="handled"
            onScroll={event => {
              scrolledAway.current = event.nativeEvent.contentOffset.y > 40;
            }}
            scrollEventThrottle={100}
            contentContainerStyle={[
              styles.conversationList,
              embedded && mobileStyles.list,
            ]}
            style={styles.conversationListPane}>
            {notice && (
              <Text
                accessibilityRole="alert"
                style={styles.projectionEmptyCopy}>
                {notice}
              </Text>
            )}
            {loading && outcome === null ? (
              <View
                style={[
                  styles.projectionEmpty,
                  embedded && mobileStyles.state,
                ]}>
                {embedded ? (
                  <OmiAvatar
                    tone="ink"
                    size={48}
                    motion="breathe"
                    reduceMotion={reduceMotion}
                  />
                ) : (
                  <ActivityIndicator color="#888888" />
                )}
                <Text style={styles.projectionEmptyCopy}>
                  Loading conversations…
                </Text>
              </View>
            ) : error !== null ? (
              <View
                style={[
                  styles.projectionEmpty,
                  embedded && mobileStyles.state,
                ]}>
                <Text style={styles.projectionEmptyTitle}>
                  Conversations unavailable
                </Text>
                <Text
                  accessibilityRole="alert"
                  style={styles.projectionEmptyCopy}>
                  {error}
                </Text>
              </View>
            ) : grouped.length === 0 ? (
              <View
                style={[
                  styles.projectionEmpty,
                  embedded && mobileStyles.state,
                ]}>
                {embedded && (
                  <OmiAvatar
                    tone="ink"
                    size={48}
                    motion="arrive"
                    reduceMotion={reduceMotion}
                  />
                )}
                <Text style={styles.projectionEmptyTitle}>
                  {filtering
                    ? 'No loaded conversations match.'
                    : 'No conversations yet.'}
                </Text>
                {filtering && (
                  <Text style={styles.projectionEmptyCopy}>
                    Search and filters cover conversations already loaded on
                    this device.
                  </Text>
                )}
                {embedded && !filtering && (
                  <Text style={mobileStyles.stateCopy}>
                    Your saved conversations will appear here, ready to revisit.
                  </Text>
                )}
                {embedded && filtering && (
                  <FocusPressable
                    accessibilityRole="button"
                    accessibilityLabel="Clear conversation filters"
                    onPress={() => {
                      setQuery('');
                      setStarredOnly(false);
                    }}
                    style={mobileStyles.reset}>
                    <Text style={mobileStyles.filterTextSelected}>
                      Clear filters
                    </Text>
                  </FocusPressable>
                )}
              </View>
            ) : (
              grouped.map(group => (
                <View key={group.label} style={styles.conversationGroup}>
                  <Text style={styles.conversationGroupTitle}>
                    {group.label}
                  </Text>
                  {group.items.map(item => (
                    <ConversationRow
                      item={item}
                      embedded={embedded}
                      key={item.id}
                      onPress={() => {
                        if (compact) scrolledAway.current = false;
                        setSelectedId(item.id);
                      }}
                      selected={selectedId === item.id}
                    />
                  ))}
                </View>
              ))
            )}
            {outcome?.status === 'success' &&
              outcome.value.page.hasMore &&
              onLoadMore && (
                <FocusPressable
                  accessibilityRole="button"
                  accessibilityLabel="Load more conversations"
                  disabled={loading || loadingMore}
                  onPress={() => {
                    // A first-page refresh would discard the older rows.
                    paginated.current = true;
                    onLoadMore();
                  }}
                  style={mobileStyles.pageAction}>
                  <Text style={styles.projectionEmptyCopy}>
                    {loadingMore ? 'Loading…' : 'Load more'}
                  </Text>
                </FocusPressable>
              )}
            {outcome?.status === 'success' && (
              <ReadStatus label="Conversations" page={outcome.value.page} />
            )}
          </ScrollView>
        )}
        {(!compact || selected !== null) && (
          <View style={mobileStyles.detailPane}>
            {compact && selected !== null && (
              <FocusPressable
                accessibilityRole="button"
                accessibilityLabel="Back to conversations"
                onPress={() => setSelectedId(null)}
                style={mobileStyles.back}>
                <ChevronLeft size={20} color={mobileColor.text} />
                <Text style={mobileStyles.filterTextSelected}>
                  Conversations
                </Text>
              </FocusPressable>
            )}
            <ScrollView
              accessibilityLabel="Selected conversation details"
              contentContainerStyle={[
                styles.conversationDetailContent,
                embedded && mobileStyles.detailContent,
              ]}
              style={[
                styles.conversationDetail,
                embedded && mobileStyles.detail,
              ]}>
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
                  <ConversationDetail
                    conversation={selected}
                    apiContract={
                      outcome?.status === 'success'
                        ? outcome.value.apiContract
                        : undefined
                    }
                  />
                </>
              )}
            </ScrollView>
          </View>
        )}
      </View>
    </View>
  );
}

const mobileStyles = StyleSheet.create({
  pageAction: {minHeight: 44, justifyContent: 'center'},
  page: {paddingHorizontal: 20, paddingVertical: 16},
  embedded: {paddingTop: 0, paddingBottom: 0, paddingHorizontal: 16},
  discovery: {
    marginTop: 0,
    flexDirection: 'column',
    alignItems: 'stretch',
    gap: 12,
  },
  search: {
    flex: 0,
    minHeight: 52,
    paddingRight: 4,
    backgroundColor: mobileColor.surface,
    borderColor: mobileColor.border,
    borderRadius: 16,
  },
  searchInput: {minWidth: 0, fontSize: 16},
  clear: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  filters: {
    flexDirection: 'row',
    gap: 6,
    padding: 4,
    borderRadius: 16,
    backgroundColor: mobileColor.surfaceQuiet,
  },
  filter: {
    flex: 1,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
    borderWidth: 0,
    backgroundColor: 'transparent',
  },
  filterSelected: {backgroundColor: mobileColor.surfaceRaised},
  filterText: {color: mobileColor.textMuted, fontSize: 14, fontWeight: '500'},
  filterTextSelected: {
    color: mobileColor.text,
    fontSize: 14,
    fontWeight: '600',
  },
  content: {flexDirection: 'column'},
  list: {flexGrow: 1},
  state: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 16,
    padding: 24,
  },
  stateCopy: {
    color: mobileColor.textMuted,
    fontSize: 14,
    lineHeight: 22,
    textAlign: 'center',
  },
  reset: {
    minHeight: 44,
    paddingHorizontal: 20,
    justifyContent: 'center',
    borderRadius: 14,
    backgroundColor: mobileColor.surfaceRaised,
  },
  meta: {color: mobileColor.textSubtle, fontSize: 12},
  detailPane: {flex: 1},
  back: {
    minHeight: 48,
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: 6,
    paddingRight: 14,
    marginBottom: 12,
  },
  detail: {
    borderWidth: 0,
    backgroundColor: 'transparent',
    borderRadius: 0,
  },
  detailContent: {padding: 4, paddingBottom: 32},
  card: {
    borderRadius: 22,
    padding: 18,
    backgroundColor: mobileColor.surface,
    borderColor: mobileColor.border,
  },
  title: {fontSize: 17, lineHeight: 24, marginTop: 12},
  summary: {
    fontSize: 14,
    lineHeight: 21,
    color: mobileColor.textMuted,
    marginTop: 6,
  },
});
