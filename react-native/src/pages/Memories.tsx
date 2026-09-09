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
  desktopBackendUnavailableCopy,
  loadMemories,
  memoryDisplayBody,
  memoryDisplayTitle,
  memoryCitationCopy,
  memorySynthesisCopy,
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
  return new Date(timestamp * 1000).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
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
      const next = await loadMemories(omiBackend, page.nextCursor);
      if (attempt !== generation.current) {
        return;
      }
      setItems(current => {
        const ids = new Set(current.map(item => item.id));
        return [...current, ...next.items.filter(item => !ids.has(item.id))];
      });
      setPage(next.page);
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
