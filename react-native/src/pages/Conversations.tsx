import React, {memo, useEffect, useMemo, useRef, useState} from 'react';
import {
  ActivityIndicator,
  Platform,
  ScrollView,
  Text,
  TextInput,
  View,
} from 'react-native';
import Search from 'lucide-react-native/icons/search';
import {
  conversationGroupLabel,
  type ConversationProjection,
  type DesktopReadProjection,
  type DomainReadOutcome,
} from '../desktopReadClient';
import {FocusPressable} from '../ui/Pressable';
import {ReadStatus} from '../ui/ReadStatus';
import {styles} from '../ui/styles';

function formatConversationDate(value: string | null): string {
  if (value === null) {
    return 'Time unavailable';
  }
  return new Intl.DateTimeFormat(undefined, {
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    month: 'short',
  }).format(new Date(value));
}

function formatConversationDuration(
  startedAt: string | null,
  finishedAt: string | null,
): string {
  if (startedAt === null || finishedAt === null) {
    return 'Duration unavailable';
  }
  const duration = Date.parse(finishedAt) - Date.parse(startedAt);
  if (!Number.isFinite(duration) || duration < 0) {
    return 'Duration unavailable';
  }
  const minutes = Math.round(duration / 60_000);
  if (minutes < 60) {
    return `${minutes} min`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes === 0
    ? `${hours} hr`
    : `${hours} hr ${remainingMinutes} min`;
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
}: {
  outcome: DomainReadOutcome<DesktopReadProjection> | null;
  loading: boolean;
}) {
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
    <View style={styles.conversationPage}>
      <Text
        style={[
          styles.projectionTitle,
          Platform.OS === 'macos' && styles.macPrimaryText,
        ]}>
        Conversations
      </Text>
      <View style={styles.recapStatus}>
        <Text style={styles.destinationSectionTitle}>Daily recaps</Text>
        <Text style={styles.projectionEmptyCopy}>
          Recaps unavailable. The v5 backend does not expose a daily recap
          projection, so no recap cards or actions are shown.
        </Text>
      </View>
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
      <View style={styles.conversationContent}>
        <ScrollView
          contentContainerStyle={styles.conversationList}
          style={styles.conversationListPane}>
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
              <Text style={styles.projectionEmptyCopy}>
                Conversations could not be loaded.
              </Text>
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
                  Search and filters cover conversations already loaded on this
                  device.
                </Text>
              )}
            </View>
          ) : (
            grouped.map(group => (
              <View key={group.label} style={styles.conversationGroup}>
                <Text style={styles.conversationGroupTitle}>{group.label}</Text>
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
          {outcome?.status === 'success' && (
            <ReadStatus label="Conversations" page={outcome.value.page} />
          )}
        </ScrollView>
        <View
          accessibilityLabel="Selected conversation metadata"
          style={styles.conversationDetail}>
          {selected === null ? (
            <View style={styles.conversationDetailEmpty}>
              <Text style={styles.projectionEmptyTitle}>
                Select a conversation
              </Text>
              <Text style={styles.projectionEmptyCopy}>
                Choose a loaded row to review its saved metadata.
              </Text>
            </View>
          ) : (
            <>
              <Text style={styles.conversationDetailEyebrow}>
                LOADED LIST METADATA
              </Text>
              <Text style={styles.conversationDetailTitle}>
                {selected.title}
              </Text>
              <Text style={styles.conversationDetailSummary}>
                {selected.summary}
              </Text>
              <View style={styles.conversationDetailFields}>
                <Text style={styles.conversationDetailField}>
                  Started · {formatConversationDate(selected.startedAt)}
                </Text>
                <Text style={styles.conversationDetailField}>
                  Finished · {formatConversationDate(selected.finishedAt)}
                </Text>
                <Text style={styles.conversationDetailField}>
                  Duration ·{' '}
                  {formatConversationDuration(
                    selected.startedAt,
                    selected.finishedAt,
                  )}
                </Text>
                <Text style={styles.conversationDetailField}>
                  Status · {selected.status}
                </Text>
                <Text style={styles.conversationDetailField}>
                  {selected.locked ? 'Locked record' : 'Unlocked record'}
                </Text>
                <Text style={styles.conversationDetailField}>
                  {selected.discarded ? 'Discarded record' : 'Active record'}
                </Text>
              </View>
              <Text style={styles.conversationDetailNotice}>
                No fetched conversation detail, transcript, playback, folders,
                or actions are shown here.
              </Text>
            </>
          )}
        </View>
      </View>
    </View>
  );
}
