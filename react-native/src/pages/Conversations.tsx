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
import {styles} from '../ui/styles';

const ConversationRow = memo(function ConversationRow({
  item,
  selected,
  onPress,
}: {
  item: ConversationProjection;
  selected: boolean;
  onPress: () => void;
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
        <Text
          accessibilityLabel={
            item.starred ? 'Starred conversation' : 'Not starred'
          }
          style={styles.conversationRowStar}>
          {item.starred ? '★' : '☆'}
        </Text>
      </View>
      <Text numberOfLines={1} style={styles.resultTitle}>
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

export function ConversationsPage({
  outcome,
  loading,
  embedded = false,
  onRefresh,
  onLoadMore,
  loadingMore = false,
  notice = null,
}: {
  outcome: DomainReadOutcome<DesktopReadProjection> | null;
  loading: boolean;
  embedded?: boolean;
  onRefresh?: () => void;
  onLoadMore?: () => void;
  loadingMore?: boolean;
  notice?: string | null;
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
  const nowEpochMilliseconds = useRef(Date.now()).current;
  const selected = conversations.find(item => item.id === selectedId) ?? null;
  const error = outcome?.status === 'error' ? outcome.error : null;
  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return conversations.filter(
      item =>
        (!starredOnly || item.starred) &&
        (normalized === '' ||
          item.title.toLocaleLowerCase().includes(normalized) ||
          item.summary.toLocaleLowerCase().includes(normalized)),
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
      )}
      <View style={styles.conversationContent}>
        {(!compact || selected === null) && (
          <ScrollView
            contentContainerStyle={styles.conversationList}
            style={styles.conversationListPane}>
            {onRefresh && (
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
                      key={item.id}
                      onPress={() => setSelectedId(item.id)}
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
                  onPress={onLoadMore}
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
