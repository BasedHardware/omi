import React, {useCallback, useEffect, useMemo, useState} from 'react';
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
  loadMemories,
  type DesktopReadProjection,
  type DomainReadOutcome,
  type MemoryProjection,
  type ReadPageState,
} from '../desktopReadClient';
import {omiBackend} from '../omiNative';
import {FocusPressable} from '../ui/Pressable';
import {ReadStatus} from '../ui/ReadStatus';
import {styles} from '../ui/styles';

function formatMemoryDate(timestamp: number | null): string {
  if (timestamp === null) {
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
}: {
  outcome: DomainReadOutcome<DesktopReadProjection> | null;
  loading: boolean;
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
  const [loadMoreError, setLoadMoreError] = useState(false);
  useEffect(() => {
    if (outcome?.status === 'success') {
      setItems(loaded);
      setPage(outcome.value.page);
      setLoadMoreError(false);
    }
  }, [loaded, outcome]);
  const results = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return normalized === ''
      ? items
      : items.filter(item =>
          item.searchableText.toLocaleLowerCase().includes(normalized),
        );
  }, [items, query]);
  const loadMore = async () => {
    if (
      omiBackend === null ||
      omiBackend === undefined ||
      page?.nextCursor === null ||
      page?.nextCursor === undefined ||
      loadingMore
    ) {
      return;
    }
    setLoadingMore(true);
    setLoadMoreError(false);
    try {
      const next = await loadMemories(omiBackend, page.nextCursor);
      setItems(current => {
        const ids = new Set(current.map(item => item.id));
        return [...current, ...next.items.filter(item => !ids.has(item.id))];
      });
      setPage(next.page);
    } catch {
      setLoadMoreError(true);
    } finally {
      setLoadingMore(false);
    }
  };
  const renderItem = useCallback(
    ({item}: {item: MemoryProjection}) => (
      <View
        accessibilityLabel={`Memory: ${item.title}`}
        style={styles.memoryCard}>
        <View style={styles.memoryMetaRow}>
          <Text style={styles.memoryTimestamp}>
            {formatMemoryDate(item.timestamp)}
          </Text>
          <Text style={styles.memoryCitationCount}>
            {item.citations.length === 1
              ? '1 citation'
              : `${item.citations.length} citations`}
          </Text>
        </View>
        <Text style={styles.memoryBody}>{item.summary}</Text>
        <Text style={styles.memoryProvenance}>Synthesized memory</Text>
      </View>
    ),
    [],
  );
  const error = outcome?.status === 'error' ? outcome.error : null;
  const filtering = query.trim() !== '';
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
                {filtering ? 'No loaded memories match.' : 'No memories yet.'}
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
                <ReadStatus label="Memories" page={page} />
                {page.hasMore && page.nextCursor !== null && (
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
                      {loadingMore ? 'Loading more…' : 'Load more'}
                    </Text>
                  </FocusPressable>
                )}
                {loadMoreError && (
                  <Text style={styles.error}>
                    More memories could not be loaded.
                  </Text>
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
