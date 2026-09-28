import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {
  ActivityIndicator,
  FlatList,
  Platform,
  Text,
  TextInput,
  View,
} from 'react-native';
import {MaterialIcon} from '../ui/MaterialIcon';

import {
  loadMemories,
  type DesktopReadProjection,
  type DomainReadOutcome,
  type MemoryProjection,
  type ReadPageState,
} from '../desktopReadClient';
import {matchesSearchQuery} from '../searchText';
import {omiBackend} from '../omiNative';
import {createMemory} from '../legacyOmiWrites';
import {MemoryWriteActions} from './MemoryWriteActions';
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
  onRefresh,
}: {
  outcome: DomainReadOutcome<DesktopReadProjection> | null;
  loading: boolean;
  onRefresh?: () => void | Promise<void>;
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
  const [draft, setDraft] = useState('');
  const [creating, setCreating] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [writeMessage, setWriteMessage] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState(false);
  const generation = useRef(0);
  const activeRequest = useRef(false);
  useEffect(() => {
    const currentGeneration = ++generation.current;
    activeRequest.current = false;
    setItems(loaded);
    setPage(outcome?.status === 'success' ? outcome.value.page : null);
    setLoadingMore(false);
    setLoadMoreError(false);
    return () => {
      generation.current = currentGeneration + 1;
      activeRequest.current = false;
    };
  }, [loaded, outcome]);
  const results = useMemo(
    () => items.filter(item => matchesSearchQuery(item.searchableText, query)),
    [items, query],
  );
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
    setLoadMoreError(false);
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
    } catch {
      if (attempt === generation.current) {
        setLoadMoreError(true);
      }
    } finally {
      if (attempt === generation.current) {
        activeRequest.current = false;
        setLoadingMore(false);
      }
    }
  };
  const refreshMemories = async () => {
    if (omiBackend == null) throw new Error('Memory service is unavailable');
    const refreshed = await loadMemories(omiBackend);
    setItems(refreshed.items);
    setPage(refreshed.page);
    await onRefresh?.();
  };
  const addMemory = async () => {
    if (omiBackend == null || draft.trim() === '') return;
    setCreating(true);
    setWriteMessage(null);
    try {
      const result = await createMemory(omiBackend, draft.trim());
      if (!result.ok) {
        setWriteMessage(result.failure.detail);
        return;
      }
      await refreshMemories();
      setSelectedId(result.value.id);
      setDraft('');
    } catch {
      setWriteMessage('Memory saved, but the list could not be refreshed.');
    } finally {
      setCreating(false);
    }
  };
  const selected = items.find(item => item.id === selectedId) ?? null;
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
      <View style={{gap: 8, marginBottom: 14}}>
        <TextInput
          accessibilityLabel="New memory content"
          multiline
          onChangeText={setDraft}
          placeholder="Add a memory"
          placeholderTextColor="#666666"
          style={{minHeight: 54, padding: 8, borderWidth: 1}}
          value={draft}
        />
        <FocusPressable
          accessibilityRole="button"
          accessibilityLabel="Add memory"
          disabled={
            creating ||
            draft.trim() === '' ||
            outcome?.status !== 'success' ||
            outcome.value.apiContract !== 'omi'
          }
          onPress={() => void addMemory()}>
          <Text>{creating ? 'Adding…' : 'Add memory'}</Text>
        </FocusPressable>
        {writeMessage ? (
          <Text accessibilityRole="alert">{writeMessage}</Text>
        ) : null}
      </View>
      <View style={styles.memorySearchBox}>
        <MaterialIcon
          name="search"
          accessible={false}
          color="#777777"
          size={17}
        />
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
        <>
          {selected !== null ? (
            <View
              accessibilityLabel="Selected memory details"
              style={{gap: 8, marginBottom: 12}}>
              <Text accessibilityRole="header">{selected.title}</Text>
              <Text selectable>{selected.summary}</Text>
              <MemoryWriteActions
                memory={selected}
                writesAvailable={
                  outcome?.status === 'success' &&
                  outcome.value.apiContract === 'omi'
                }
                onRefresh={refreshMemories}
                onDeleted={() => setSelectedId(null)}
              />
            </View>
          ) : null}
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
            renderItem={({item}) => (
              <FocusPressable
                accessibilityRole="button"
                accessibilityLabel={`Open memory ${item.title}`}
                onPress={() => setSelectedId(item.id)}>
                {renderItem({item})}
              </FocusPressable>
            )}
          />
        </>
      )}
    </View>
  );
}
