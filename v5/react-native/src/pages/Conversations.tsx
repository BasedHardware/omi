import React, {memo, useEffect, useMemo, useRef, useState} from 'react';
import {
  AppState,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  useWindowDimensions,
} from 'react-native';
import {MaterialIcon} from '../ui/MaterialIcon';

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
import {useOmiStyles, useOmiTheme} from '../design/OmiTheme';
import {OmiButton, OmiChip, OmiPageState} from '../design/primitives';
import type {OmiTheme} from '../design/tokens';
import {
  MobileGroup,
  MobileRow,
  MobileSectionHeader,
} from '../mobile/MobileList';
import {epochOf, mobileDayLabel, mobileTimeLabel} from '../mobile/mobileDates';
import {omiBackend} from '../omiNative';
import {
  listFolders,
  setConversationStarred,
  type LegacyFolder,
} from '../legacyOmiWrites';

const ConversationRow = memo(function ConversationRow({
  item,
  selected,
  onPress,
  starred,
  onToggleStar,
}: {
  item: ConversationProjection;
  selected: boolean;
  onPress: () => void;
  starred: boolean;
  onToggleStar: () => void;
}) {
  return (
    <FocusPressable
      accessibilityLabel={`Open conversation ${item.title}`}
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
          {formatConversationDate(item.startedAt ?? item.createdAt)}
        </Text>
        <StarButton starred={starred} onToggle={onToggleStar} />
      </View>
      <Text numberOfLines={2} style={styles.resultTitle}>
        {item.title}
      </Text>
      <Text numberOfLines={2} style={styles.resultSummary}>
        {item.summary}
      </Text>
      <Text style={styles.conversationRowDuration}>
        {formatConversationDuration(item.startedAt, item.finishedAt)}
      </Text>
    </FocusPressable>
  );
});

function StarButton({
  starred,
  onToggle,
  mobile = false,
}: {
  starred: boolean;
  onToggle: () => void;
  mobile?: boolean;
}) {
  const theme = useOmiTheme();
  const local = useOmiStyles(createMobileStyles);
  return (
    <FocusPressable
      accessibilityLabel={starred ? 'Unstar conversation' : 'Star conversation'}
      accessibilityRole="button"
      onPress={event => {
        event?.stopPropagation?.();
        onToggle();
      }}
      style={mobile ? local.star : styles.conversationStarFilter}>
      <Text
        style={[
          styles.conversationRowStar,
          mobile && {
            color: starred ? theme.color.warning : theme.color.inkTertiary,
          },
        ]}>
        {starred ? '★' : '☆'}
      </Text>
    </FocusPressable>
  );
}

/** Mobile row: one shape for every conversation; the day header carries the date. */
const MobileConversationRow = memo(function MobileConversationRow({
  item,
  onPress,
  starred,
  onToggleStar,
}: {
  item: ConversationProjection;
  onPress: () => void;
  starred: boolean;
  onToggleStar: () => void;
}) {
  return (
    <MobileRow
      accessibilityLabel={`Open conversation ${item.title}`}
      onPress={onPress}
      title={item.title || 'Untitled conversation'}
      titleStyle={item.title ? 'default' : 'placeholder'}
      titleLines={2}
      trailingText={mobileTimeLabel(epochOf(item.startedAt ?? item.createdAt))}
      subtitle={item.summary === '' ? null : item.summary}
      trailing={<StarButton mobile starred={starred} onToggle={onToggleStar} />}
    />
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
  initialSelectedId = null,
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
  /** Opens this conversation's detail on mount (design preview). */
  initialSelectedId?: string | null;
}) {
  const compact = useWindowDimensions().width < 720;
  const theme = useOmiTheme();
  const local = useOmiStyles(createMobileStyles);
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
  const [selectedId, setSelectedId] = useState<string | null>(
    initialSelectedId,
  );
  const [localQuery, setLocalQuery] = useState('');
  const query = search?.value ?? localQuery;
  const setQuery = search?.onChange ?? setLocalQuery;
  const [starredOnly, setStarredOnly] = useState(false);
  const [starOverrides, setStarOverrides] = useState<Record<string, boolean>>(
    {},
  );
  const [deletedIds, setDeletedIds] = useState<Set<string>>(() => new Set());
  const [folders, setFolders] = useState<LegacyFolder[]>([]);
  const [folderFilter, setFolderFilter] = useState<string | null>(null);
  const desktopFolders = !embedded && Platform.OS === 'macos';
  useEffect(() => {
    if (!desktopFolders || !omiBackend) return;
    void listFolders(omiBackend).then(result => {
      if (result.ok) setFolders(result.value);
    });
  }, [desktopFolders]);
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
        !deletedIds.has(item.id) &&
        (!starredOnly || (starOverrides[item.id] ?? item.starred)) &&
        (folderFilter === null || item.folderId === folderFilter) &&
        (matchesSearchQuery(item.title, query) ||
          matchesSearchQuery(item.summary, query)),
    );
  }, [
    conversations,
    query,
    starredOnly,
    starOverrides,
    deletedIds,
    folderFilter,
  ]);
  useEffect(() => {
    if (selectedId !== null && !filtered.some(item => item.id === selectedId)) {
      setSelectedId(null);
    }
  }, [filtered, selectedId]);
  const grouped = useMemo(
    () =>
      filtered.reduce<Array<{label: string; items: ConversationProjection[]}>>(
        (groups, item) => {
          const at = item.startedAt ?? item.createdAt;
          // Mobile reads "Today · Yesterday · Wed, Sep 23"; the wide list
          // keeps the shared desktop grouping.
          const label = embedded
            ? mobileDayLabel(epochOf(at), nowEpochMilliseconds)
            : conversationGroupLabel(at, nowEpochMilliseconds);
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
    [filtered, nowEpochMilliseconds, embedded],
  );
  const filtering = query.trim() !== '' || starredOnly || folderFilter !== null;
  const toggleStar = async (item: ConversationProjection) => {
    const next = !(starOverrides[item.id] ?? item.starred);
    setStarOverrides(current => ({...current, [item.id]: next}));
    if (!omiBackend) return;
    const result = await setConversationStarred(omiBackend, item.id, next);
    if (!result.ok) {
      setStarOverrides(current => ({...current, [item.id]: item.starred}));
      return;
    }
    onRefresh?.();
  };

  const clearFilters = () => {
    setQuery('');
    setStarredOnly(false);
  };
  const loadMore =
    outcome?.status === 'success' &&
    outcome.value.page.hasMore &&
    onLoadMore ? (
      <OmiButton
        label={loadingMore ? 'Loading…' : 'Load More'}
        accessibilityLabel="Load more conversations"
        compact
        disabled={loading || loadingMore}
        onPress={() => {
          // A first-page refresh would discard the older rows.
          paginated.current = true;
          onLoadMore();
        }}
        style={local.loadMore}
      />
    ) : null;
  const listState =
    loading && outcome === null ? (
      <OmiPageState kind="loading" label="Loading conversations…" />
    ) : error !== null ? (
      <View accessibilityRole="alert">
        <OmiPageState
          kind="error"
          title="Couldn’t Load Conversations"
          message={error}
          onRetry={onRefresh}
        />
      </View>
    ) : grouped.length === 0 ? (
      filtering ? (
        <OmiPageState
          kind="empty"
          icon="search"
          title="No Matches"
          message="Search and filters cover conversations already loaded on this device."
          action={
            embedded
              ? {label: 'Clear Filters', onPress: clearFilters}
              : undefined
          }
        />
      ) : (
        <OmiPageState
          kind="empty"
          icon="forum"
          title="No Conversations Yet"
          message="Your saved conversations will appear here, ready to revisit."
        />
      )
    ) : null;

  if (embedded) {
    return (
      <View style={local.page}>
        {selected === null && (
          <View style={local.discovery}>
            {!search && (
              <View style={local.search}>
                <MaterialIcon
                  name="search"
                  accessible={false}
                  color={theme.color.inkTertiary}
                  size={theme.size.iconSmall}
                />
                <TextInput
                  accessibilityLabel="Search loaded conversations"
                  onChangeText={setQuery}
                  placeholder="Search conversations…"
                  placeholderTextColor={theme.color.inkTertiary}
                  keyboardAppearance={theme.scheme}
                  style={local.searchInput}
                  value={query}
                />
                {query.length > 0 && (
                  <FocusPressable
                    accessibilityRole="button"
                    accessibilityLabel="Clear conversation search"
                    onPress={() => setQuery('')}
                    style={local.clear}>
                    <MaterialIcon
                      name="close"
                      size={theme.size.iconSmall}
                      color={theme.color.inkSecondary}
                    />
                  </FocusPressable>
                )}
              </View>
            )}
            <View accessibilityLabel="Conversation filters" style={local.chips}>
              <OmiChip
                label="All"
                selected={!starredOnly}
                onPress={() => setStarredOnly(false)}
              />
              <OmiChip
                label="Starred"
                selected={starredOnly}
                onPress={() => setStarredOnly(true)}
              />
            </View>
          </View>
        )}
        {selected === null ? (
          <ScrollView
            keyboardShouldPersistTaps="handled"
            onScroll={event => {
              scrolledAway.current = event.nativeEvent.contentOffset.y > 40;
            }}
            scrollEventThrottle={100}
            contentContainerStyle={local.list}
            style={local.flex}>
            {notice && (
              <Text accessibilityRole="alert" style={local.notice}>
                {notice}
              </Text>
            )}
            {listState ??
              grouped.map(group => (
                <View key={group.label} style={local.group}>
                  <MobileSectionHeader title={group.label} />
                  <MobileGroup>
                    {group.items.map(item => (
                      <MobileConversationRow
                        item={item}
                        key={item.id}
                        starred={starOverrides[item.id] ?? item.starred}
                        onToggleStar={() => {
                          toggleStar(item).catch(() => undefined);
                        }}
                        onPress={() => {
                          scrolledAway.current = false;
                          setSelectedId(item.id);
                        }}
                      />
                    ))}
                  </MobileGroup>
                </View>
              ))}
            {loadMore}
            {outcome?.status === 'success' && (
              <ReadStatus label="Conversations" page={outcome.value.page} />
            )}
          </ScrollView>
        ) : (
          <View style={local.flex}>
            <FocusPressable
              accessibilityRole="button"
              accessibilityLabel="Back to conversations"
              onPress={() => setSelectedId(null)}
              style={({pressed}) => [local.back, pressed && local.pressed]}>
              <MaterialIcon
                name="chevron_left"
                size={theme.size.icon + 4}
                color={theme.color.ink}
              />
              <Text style={local.backText}>Conversations</Text>
            </FocusPressable>
            <ScrollView
              accessibilityLabel="Selected conversation details"
              contentContainerStyle={local.detailContent}
              style={local.flex}>
              <ConversationDetail
                conversation={selected}
                desktop={false}
                onRefresh={onRefresh}
                onDeleted={() => {
                  setDeletedIds(current => new Set(current).add(selected.id));
                  setSelectedId(null);
                  onRefresh?.();
                }}
                apiContract={
                  outcome?.status === 'success'
                    ? outcome.value.apiContract
                    : undefined
                }
              />
            </ScrollView>
          </View>
        )}
      </View>
    );
  }

  return (
    <View style={[styles.conversationPage, compact && mobileStyles.page]}>
      <Text
        style={[
          styles.projectionTitle,
          Platform.OS === 'macos' && styles.macPrimaryText,
        ]}>
        Conversations
      </Text>
      {(!compact || selected === null) && (
        <View style={styles.conversationDiscovery}>
          {!search && (
            <View style={styles.conversationSearchBox}>
              <MaterialIcon
                name="search"
                accessible={false}
                color="#777777"
                size={17}
              />
              <TextInput
                accessibilityLabel="Search loaded conversations"
                onChangeText={setQuery}
                placeholder="Search loaded conversations"
                placeholderTextColor="#666666"
                style={styles.memorySearchInput}
                value={query}
              />
            </View>
          )}
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
      )}
      {desktopFolders && folders.length > 0 && selected === null && (
        <View
          accessibilityLabel="Conversation folder filters"
          style={mobileStyles.filters}>
          {[{id: '', name: 'All folders'}, ...folders].map(folder => {
            const isSelected = (folder.id || null) === folderFilter;
            return (
              <FocusPressable
                key={folder.id || 'all'}
                accessibilityRole="button"
                accessibilityLabel={`Filter folder ${folder.name}`}
                accessibilityState={{selected: isSelected}}
                onPress={() => setFolderFilter(folder.id || null)}
                style={mobileStyles.filter}>
                <Text
                  style={[
                    mobileStyles.filterText,
                    isSelected && mobileStyles.filterTextSelected,
                  ]}>
                  {folder.name}
                </Text>
              </FocusPressable>
            );
          })}
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
            contentContainerStyle={styles.conversationList}
            style={styles.conversationListPane}>
            {notice && (
              <Text
                accessibilityRole="alert"
                style={styles.projectionEmptyCopy}>
                {notice}
              </Text>
            )}
            {listState ??
              grouped.map(group => (
                <View key={group.label} style={styles.conversationGroup}>
                  <Text style={styles.conversationGroupTitle}>
                    {group.label}
                  </Text>
                  {group.items.map(item => (
                    <ConversationRow
                      item={item}
                      key={item.id}
                      starred={starOverrides[item.id] ?? item.starred}
                      onToggleStar={() => void toggleStar(item)}
                      onPress={() => {
                        if (compact) scrolledAway.current = false;
                        setSelectedId(item.id);
                      }}
                      selected={selectedId === item.id}
                    />
                  ))}
                </View>
              ))}
            {loadMore}
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
                <MaterialIcon name="chevron_left" size={20} color="#ffffff" />
                <Text style={mobileStyles.filterTextSelected}>
                  Conversations
                </Text>
              </FocusPressable>
            )}
            <ScrollView
              accessibilityLabel="Selected conversation details"
              contentContainerStyle={styles.conversationDetailContent}
              style={styles.conversationDetail}>
              {selected === null ? (
                <View style={styles.conversationDetailEmpty}>
                  <Text style={styles.projectionEmptyTitle}>
                    Select a Conversation
                  </Text>
                  <Text style={styles.projectionEmptyCopy}>
                    Choose a conversation to view its summary and details.
                  </Text>
                </View>
              ) : (
                <ConversationDetail
                  conversation={selected}
                  desktop
                  onRefresh={onRefresh}
                  onDeleted={() => {
                    setDeletedIds(current => new Set(current).add(selected.id));
                    setSelectedId(null);
                    onRefresh?.();
                  }}
                  apiContract={
                    outcome?.status === 'success'
                      ? outcome.value.apiContract
                      : undefined
                  }
                />
              )}
            </ScrollView>
          </View>
        )}
      </View>
    </View>
  );
}

const createMobileStyles = (t: OmiTheme) => ({
  flex: {flex: 1},
  page: {flex: 1, paddingHorizontal: t.layout.pageGutter.mobile},
  discovery: {gap: t.space.md, paddingBottom: t.space.xs},
  search: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: t.space.sm,
    minHeight: t.size.control,
    paddingLeft: t.space.lg,
    paddingRight: t.space.xs,
    borderRadius: t.radius.pill,
    backgroundColor: t.color.surface,
  },
  searchInput: {
    ...t.type.body,
    flex: 1,
    minWidth: 0,
    minHeight: t.size.hitTarget,
    paddingVertical: 0,
    color: t.color.ink,
  },
  clear: {
    width: t.size.hitTarget,
    height: t.size.hitTarget,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
  },
  chips: {flexDirection: 'row' as const, gap: t.space.sm},
  list: {flexGrow: 1, paddingBottom: t.space.xxl},
  group: {gap: t.space.xs, marginBottom: t.space.sm},
  notice: {
    ...t.type.subhead,
    color: t.color.inkSecondary,
    paddingVertical: t.space.sm,
  },
  star: {
    width: t.size.hitTarget,
    height: t.size.hitTarget,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
  },
  loadMore: {alignSelf: 'center' as const, marginTop: t.space.sm},
  back: {
    minHeight: t.size.hitTarget,
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    alignSelf: 'flex-start' as const,
    paddingRight: t.space.md,
    marginLeft: -t.space.sm,
    marginBottom: t.space.xs,
    borderRadius: t.radius.pill,
  },
  pressed: {opacity: t.motion.pressedOpacity},
  backText: {...t.type.body, color: t.color.ink},
  detailContent: {paddingBottom: t.space.section},
});

const mobileStyles = StyleSheet.create({
  page: {paddingHorizontal: 20, paddingVertical: 16},
  filters: {
    flexDirection: 'row',
    gap: 6,
    padding: 4,
    borderRadius: 16,
    backgroundColor: '#151613',
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
  filterText: {color: '#b5b8af', fontSize: 14, fontWeight: '500'},
  filterTextSelected: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: '600',
  },
  content: {flexDirection: 'column'},
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
});
