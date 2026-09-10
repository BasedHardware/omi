import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {
  ActivityIndicator,
  FlatList,
  Platform,
  Text,
  TextInput,
  View,
} from 'react-native';
import Search from 'lucide-react-native/icons/search';
import {
  clockLabel,
  desktopBackendUnavailableCopy,
  loadMemories,
  MemoryCursorExpiredError,
  memoryDisplayBody,
  memoryDisplayTitle,
  memoryCitationCopy,
  memorySynthesisCopy,
  memoryLedgerSlotCopy,
  memoryLedgerPlaybookCopy,
  memoryBaselineCopy,
  memoryLockedCopy,
  visibleDisplayText,
  type DesktopReadProjection,
  type DomainReadOutcome,
  type MemoryProjection,
  type ReadPageState,
} from '../desktopReadClient';
import {omiBackend} from '../omiNative';
import {FocusPressable} from '../ui/Pressable';
import {ReadStatus, emptyLibraryCopy} from '../ui/ReadStatus';
import {styles} from '../ui/styles';

function formatMemoryDate(timestamp: number | null): string {
  if (timestamp === null || !Number.isFinite(timestamp) || timestamp <= 0) {
    return 'Date unavailable';
  }
  const label = clockLabel(timestamp * 1000, Date.now());
  return label === '' ? 'Date unavailable' : label;
}

export function MemoriesPage({
  outcome,
  loading,
  onRefresh,
}: {
  outcome: DomainReadOutcome<DesktopReadProjection> | null;
  loading: boolean;
  onRefresh?: () => void;
}) {
  const loaded = useMemo(
    () =>
      outcome?.status === 'success'
        ? outcome.value.items.filter(
            (item): item is MemoryProjection => item.kind === 'memory',
          )
        : [],
    [outcome],
  );
  const [items, setItems] = useState<MemoryProjection[]>(loaded);
  const [page, setPage] = useState<ReadPageState | null>(
    outcome?.status === 'success' ? outcome.value.page : null,
  );
  const [query, setQuery] = useState('');
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  const [loadMoreRetryable, setLoadMoreRetryable] = useState(true);
  const generation = useRef(0);
  const activeRequest = useRef(false);
  useEffect(() => {
    const currentGeneration = ++generation.current;
    activeRequest.current = false;
    setItems(loaded);
    setPage(outcome?.status === 'success' ? outcome.value.page : null);
    setLoadingMore(false);
    setLoadMoreError(null);
    setLoadMoreRetryable(true);
    return () => {
      generation.current = currentGeneration + 1;
      activeRequest.current = false;
    };
  }, [loaded, outcome]);
  const results = useMemo(() => {
    const normalized = visibleDisplayText(query).toLocaleLowerCase();
    return normalized === ''
      ? items
      : items.filter(item =>
          `${item.searchableText}\n${memoryDisplayTitle(
            item,
          )}\n${memoryDisplayBody(item)}`
            .toLocaleLowerCase()
            .includes(normalized),
        );
  }, [items, query]);
  const loadMore = async () => {
    if (
      omiBackend === null ||
      omiBackend === undefined ||
      outcome?.status !== 'success' ||
      page?.nextCursor === null ||
      page?.nextCursor === undefined ||
      activeRequest.current
    ) {
      return;
    }
    const attempt = generation.current;
    activeRequest.current = true;
    setLoadingMore(true);
    setLoadMoreError(null);
    setLoadMoreRetryable(true);
    try {
      let replace = false;
      let next;
      try {
        next = await loadMemories(omiBackend, page.nextCursor);
      } catch (reason) {
        if (
          !(reason instanceof MemoryCursorExpiredError) ||
          attempt !== generation.current
        ) {
          throw reason;
        }
        replace = true;
        next = await loadMemories(omiBackend);
      }
      if (attempt !== generation.current) {
        return;
      }
      if (replace) {
        setItems(next.items);
        setPage(next.page);
        setLoadMoreError('Memories changed. The list has been refreshed.');
      } else {
        setItems(current => {
          const ids = new Set(current.map(item => item.id));
          return [...current, ...next.items.filter(item => !ids.has(item.id))];
        });
        setPage(next.page);
      }
    } catch (reason) {
      if (attempt === generation.current) {
        const unavailable =
          reason instanceof Error &&
          reason.message === desktopBackendUnavailableCopy;
        setLoadMoreRetryable(!unavailable);
        setLoadMoreError(
          unavailable
            ? desktopBackendUnavailableCopy
            : 'More memories could not be loaded.',
        );
      }
    } finally {
      if (attempt === generation.current) {
        activeRequest.current = false;
        setLoadingMore(false);
      }
    }
  };
  const renderItem = useCallback(({item}: {item: MemoryProjection}) => {
    const synthesis = memorySynthesisCopy(item);
    const slot = memoryLedgerSlotCopy(item);
    const playbook = memoryLedgerPlaybookCopy(item);
    const baseline = memoryBaselineCopy(item);
    const locked = memoryLockedCopy(item);
    const device = visibleDisplayText(item.captureDeviceLabel ?? '');
    return (
      <View
        accessibilityLabel={`Memory: ${memoryDisplayBody(item)}`}
        style={styles.memoryCard}>
        <View style={styles.memoryMetaRow}>
          <Text style={styles.memoryTimestamp}>
            {formatMemoryDate(item.timestamp)}
          </Text>
          <Text style={styles.memoryCitationCount}>
            {memoryCitationCopy(item.citations)}
          </Text>
        </View>
        <Text style={styles.memoryBody}>{memoryDisplayBody(item)}</Text>
        {slot !== null ? (
          <Text style={styles.memoryProvenance}>{slot}</Text>
        ) : null}
        {playbook !== null ? (
          <Text numberOfLines={3} style={styles.memoryProvenance}>
            {playbook}
          </Text>
        ) : null}
        {device !== '' ? (
          <Text style={styles.memoryProvenance}>{device}</Text>
        ) : null}
        {baseline !== null ? (
          <Text style={styles.memoryProvenance}>{baseline}</Text>
        ) : null}
        {locked !== null ? (
          <Text
            accessibilityLabel="Locked memory"
            style={styles.memoryProvenance}>
            {locked}
          </Text>
        ) : null}
        {synthesis !== null ? (
          <Text style={styles.memoryProvenance}>{synthesis}</Text>
        ) : null}
      </View>
    );
  }, []);
  const error = outcome?.status === 'error' ? outcome.error : null;
  const filtering = visibleDisplayText(query) !== '';
  return (
    <View style={styles.memoryPage}>
      <Text
        style={[
          styles.projectionTitle,
          Platform.OS === 'macos' && styles.macPrimaryText,
        ]}>
        Memories
      </Text>
      <View style={styles.memorySearchBox}>
        <Search accessible={false} color="#777777" size={17} />
        <TextInput
          accessibilityLabel="Search loaded memories"
          onChangeText={setQuery}
          placeholder="Search loaded memories"
          placeholderTextColor="#666666"
          style={styles.memorySearchInput}
          value={query}
        />
      </View>
      {onRefresh && error !== desktopBackendUnavailableCopy && (
        <FocusPressable
          accessibilityRole="button"
          accessibilityLabel="Refresh memories"
          disabled={loading || loadingMore}
          onPress={onRefresh}
          style={{minHeight: 44, justifyContent: 'center'}}>
          <Text style={styles.projectionEmptyCopy}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </Text>
        </FocusPressable>
      )}
      {loading && outcome === null ? (
        <View style={styles.projectionEmpty}>
          <ActivityIndicator color="#888888" />
          <Text style={styles.projectionEmptyCopy}>Loading memories…</Text>
        </View>
      ) : error !== null ? (
        <View style={styles.projectionEmpty}>
          <Text style={styles.projectionEmptyTitle}>Memories unavailable</Text>
          <Text style={styles.projectionEmptyCopy}>{error}</Text>
        </View>
      ) : (
        <FlatList
          contentContainerStyle={styles.memoryList}
          data={results}
          keyExtractor={item => item.id}
          ListEmptyComponent={
            <View style={styles.projectionEmpty}>
              <Text style={styles.projectionEmptyTitle}>
                {emptyLibraryCopy(
                  'Memories',
                  page,
                  filtering,
                  'No loaded memories match.',
                  'No memories yet.',
                  loadMoreError === desktopBackendUnavailableCopy,
                )}
              </Text>
              {filtering && (
                <Text style={styles.projectionEmptyCopy}>
                  Search covers the memories loaded on this device.
                </Text>
              )}
            </View>
          }
          ListFooterComponent={
            page === null ? null : (
              <View style={styles.memoryFooter}>
                {(results.length > 0 || filtering) && (
                  <ReadStatus
                    continueUnavailable={
                      loadMoreError === desktopBackendUnavailableCopy
                    }
                    label="Memories"
                    page={page}
                  />
                )}
                {page.hasMore &&
                  page.nextCursor !== null &&
                  loadMoreRetryable && (
                    <FocusPressable
                      accessibilityLabel="Load more memories"
                      accessibilityRole="button"
                      disabled={loadingMore}
                      onPress={loadMore}
                      style={({pressed}) => [
                        styles.loadOlderButton,
                        pressed && styles.pressed,
                      ]}>
                      <Text style={styles.loadOlderText}>
                        {loadingMore ? 'Loading more…' : 'Load more memories'}
                      </Text>
                    </FocusPressable>
                  )}
                {loadMoreError && (
                  <Text style={styles.error}>{loadMoreError}</Text>
                )}
              </View>
            )
          }
          renderItem={renderItem}
        />
      )}
    </View>
  );
}
