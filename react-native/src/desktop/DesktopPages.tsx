import React, {useEffect, useState} from 'react';
import {ScrollView, StyleSheet, Text, View} from 'react-native';
import Puzzle from 'lucide-react-native/icons/puzzle';
import ListChecks from 'lucide-react-native/icons/list-checks';
import {loadConnectors, type CloudApp} from '../desktopCloudClient';
import {
  projectionTimestamp,
  type DesktopReadOutcomes,
} from '../desktopReadClient';
import {matchesSearchQuery} from '../searchText';
import {omiBackend, subscribeOmiBackendSessionInvalidated} from '../omiNative';
import {ReadStatus} from '../ui/ReadStatus';
import {ConversationDetail} from '../ui/ConversationDetail';
import {ScrollFade, useScrollFade} from './ScrollFade';
import {FocusPressable} from '../ui/Pressable';
import {
  TaskEditor,
  TaskMutationStatus,
  type TaskMutationProps,
} from '../ui/TaskEditor';
import {ShippingListInsert, ShippingStage} from './ShippingStage';
import {ConnectionGallery} from './ConnectionGallery';
import {
  ConversationRow,
  DesktopEmptyState,
  PageHeading,
  ReadRow,
  TaskRow,
} from './DesktopRows';
import type {DesktopSession} from './desktopChrome';
import {desktopTokens as token} from './tokens';

export function LibraryPage({
  outcomes,
  query = '',
  onLoadMore,
  loadingMore = false,
  notice = null,
}: {
  outcomes: DesktopReadOutcomes | null;
  query?: string;
  onLoadMore?: () => void;
  loadingMore?: boolean;
  notice?: string | null;
}) {
  const fade = useScrollFade();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  useEffect(
    () => subscribeOmiBackendSessionInvalidated(() => setSelectedId(null)),
    [],
  );
  const outcome = outcomes?.conversations ?? null;
  const memoryOutcome = outcomes?.memories ?? null;
  const items = [
    ...(outcome?.status === 'success' ? outcome.value.items : []),
    ...(memoryOutcome?.status === 'success' ? memoryOutcome.value.items : []),
  ]
    .filter(item => matchesSearchQuery(item.searchableText, query))
    .sort(
      (left, right) =>
        (projectionTimestamp(right) ?? 0) - (projectionTimestamp(left) ?? 0),
    );
  const selected =
    items.find(item => `${item.kind}:${item.id}` === selectedId) ?? null;
  const readError = [outcome, memoryOutcome]
    .filter(value => value?.status === 'error')
    .map(value => (value?.status === 'error' ? value.error : ''))
    .join(' ');
  useEffect(() => {
    if (selectedId !== null && selected === null) {
      setSelectedId(null);
    }
  }, [selectedId, selected]);
  const emptyCopy =
    outcome === null
      ? 'Loading conversations…'
      : outcome.status === 'error'
      ? outcome.error
      : query.trim() !== ''
      ? 'No loaded conversations or memories match.'
      : 'Nothing captured in this window yet.';
  return (
    <View style={styles.page}>
      <PageHeading
        title="Conversations & memories"
        subtitle={
          query.trim() !== ''
            ? `From your loaded history, matching “${query.trim()}”.`
            : 'The moments worth coming back to.'
        }
      />
      {readError && items.length > 0 ? (
        <Text accessibilityRole="alert" style={styles.rowMeta}>
          {readError}
        </Text>
      ) : null}
      {notice ? (
        <Text accessibilityRole="alert" style={styles.rowMeta}>
          {notice}
        </Text>
      ) : null}
      {selected !== null ? (
        <ScrollFade visible style={styles.list}>
          <ScrollView
            accessibilityLabel="Selected conversation details"
            onLayout={fade.onLayout}
            onScroll={fade.onScroll}
            onContentSizeChange={fade.onContentSizeChange}
            scrollEventThrottle={16}
            contentContainerStyle={styles.conversationDetail}>
            <FocusPressable
              accessibilityRole="button"
              accessibilityLabel="Back to conversations"
              onPress={() => setSelectedId(null)}
              style={[styles.taskEdit, styles.backAction]}>
              <Text style={styles.rowMeta}>Back to conversations</Text>
            </FocusPressable>
            {selected.kind === 'conversation' ? (
              <ConversationDetail
                key={selected.id}
                conversation={selected}
                apiContract={
                  outcome?.status === 'success'
                    ? outcome.value.apiContract
                    : undefined
                }
                desktop
              />
            ) : (
              <View
                accessibilityLabel="Selected memory details"
                style={styles.memoryDetail}>
                {selected.title.trim() !== '' &&
                  !selected.summary.startsWith(selected.title) && (
                    <Text accessibilityRole="header" style={styles.rowTitle}>
                      {selected.title}
                    </Text>
                  )}
                <Text selectable style={styles.memoryBody}>
                  {selected.summary}
                </Text>
                <Text style={styles.rowMeta}>
                  {selected.timestamp === null
                    ? 'Date unavailable'
                    : new Date(selected.timestamp * 1000).toLocaleDateString()}
                </Text>
                <Text style={styles.rowMeta}>
                  {selected.citations.length}{' '}
                  {selected.citations.length === 1 ? 'citation' : 'citations'} ·{' '}
                  {selected.provenance.label || 'Synthesized memory'}
                </Text>
              </View>
            )}
          </ScrollView>
        </ScrollFade>
      ) : (
        <ScrollFade visible style={styles.list}>
          <ScrollView
            onLayout={fade.onLayout}
            onScroll={fade.onScroll}
            onContentSizeChange={fade.onContentSizeChange}
            scrollEventThrottle={16}
            contentContainerStyle={styles.listContent}>
            {items.length === 0 ? (
              <DesktopEmptyState
                error={!!readError}
                title={
                  readError
                    ? 'History is unavailable'
                    : outcome === null
                    ? 'Finding your moments…'
                    : query.trim() !== ''
                    ? 'Nothing matches yet'
                    : 'Your story starts here.'
                }
                detail={readError || emptyCopy}
              />
            ) : (
              items.map(item => (
                <FocusPressable
                  accessibilityRole="button"
                  accessibilityLabel={`Open ${item.kind} ${
                    item.title ||
                    (item.kind === 'memory'
                      ? 'Memory'
                      : item.status === 'processing'
                      ? 'Processing conversation…'
                      : 'Conversation title unavailable')
                  }`}
                  key={`${item.kind}:${item.id}`}
                  onPress={() => setSelectedId(`${item.kind}:${item.id}`)}
                  style={({pressed}) => [
                    styles.libraryRow,
                    pressed && styles.selectedRow,
                  ]}>
                  {item.kind === 'conversation' ? (
                    <ConversationRow item={item} />
                  ) : (
                    <ReadRow item={item} />
                  )}
                </FocusPressable>
              ))
            )}
            {outcome?.status === 'success' ? (
              <>
                {outcome.value.page.hasMore && onLoadMore ? (
                  <FocusPressable
                    accessibilityRole="button"
                    accessibilityLabel="Load more conversations"
                    disabled={loadingMore}
                    onPress={onLoadMore}
                    style={styles.taskEdit}>
                    <Text style={styles.rowMeta}>
                      {loadingMore ? 'Loading…' : 'Load more'}
                    </Text>
                  </FocusPressable>
                ) : null}
                <ReadStatus
                  label="Conversations"
                  mac
                  page={outcome.value.page}
                />
              </>
            ) : null}
            {memoryOutcome?.status === 'success' ? (
              <ReadStatus
                label="Memories"
                mac
                page={memoryOutcome.value.page}
              />
            ) : null}
          </ScrollView>
        </ScrollFade>
      )}
    </View>
  );
}

export function TasksPage({
  outcomes,
  taskPagination,
  onTaskToggle,
  onTaskEdit,
  busyTaskId = null,
  writesAvailable = false,
  taskMutationError = null,
  onRetryTaskMutation,
  onDismissTaskMutation,
}: TaskMutationProps & {
  outcomes: DesktopReadOutcomes | null;
  taskPagination?: React.ReactNode;
}) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const fade = useScrollFade();
  const outcome = outcomes?.tasks ?? null;
  const tasks = outcome?.status === 'success' ? outcome.value.items : [];
  const emptyCopy =
    outcome === null
      ? 'Loading tasks…'
      : outcome.status === 'error'
      ? outcome.error
      : 'No tasks yet';
  return (
    <View style={styles.page}>
      <PageHeading
        title="A little follow-through."
        subtitle="Your tasks, with room to focus on what’s next."
        eyebrow="TASKS"
      />
      <TaskMutationStatus
        desktop
        writesAvailable={writesAvailable}
        taskMutationError={taskMutationError}
        onRetryTaskMutation={onRetryTaskMutation}
        onDismissTaskMutation={onDismissTaskMutation}
      />
      <ScrollFade visible style={styles.list}>
        <ScrollView
          onLayout={fade.onLayout}
          onScroll={fade.onScroll}
          onContentSizeChange={fade.onContentSizeChange}
          scrollEventThrottle={16}
          contentContainerStyle={styles.listContent}>
          {tasks.length > 0 ? (
            tasks.map(item => {
              const editable =
                outcome?.status === 'success' &&
                (outcome.value.apiContract === 'omi' || item.revision !== null);
              return (
                <ShippingListInsert itemKey={item.id} key={item.id}>
                  <View style={styles.libraryRow}>
                    <View style={styles.taskActions}>
                      <FocusPressable
                        accessibilityRole={
                          writesAvailable && onTaskToggle ? 'checkbox' : 'text'
                        }
                        accessibilityLabel={`${
                          item.completed ? 'Reopen' : 'Complete'
                        } task: ${item.title}`}
                        accessibilityState={{
                          checked: item.completed,
                          disabled:
                            !writesAvailable ||
                            !onTaskToggle ||
                            !editable ||
                            busyTaskId !== null,
                          busy:
                            busyTaskId === item.id &&
                            taskMutationError === null,
                        }}
                        disabled={
                          !writesAvailable ||
                          !onTaskToggle ||
                          !editable ||
                          busyTaskId !== null
                        }
                        onPress={() => onTaskToggle?.(item.id)}
                        style={styles.taskToggle}>
                        <TaskRow item={item} />
                      </FocusPressable>
                      {writesAvailable && onTaskEdit && editable && (
                        <FocusPressable
                          accessibilityRole="button"
                          accessibilityLabel={`Edit task: ${item.title}`}
                          disabled={busyTaskId !== null}
                          accessibilityState={{disabled: busyTaskId !== null}}
                          onPress={() => setEditingId(item.id)}
                          style={styles.taskEdit}>
                          <Text style={styles.rowMeta}>Edit</Text>
                        </FocusPressable>
                      )}
                    </View>
                    {editingId === item.id &&
                      writesAvailable &&
                      onTaskEdit &&
                      editable && (
                        <TaskEditor
                          desktop
                          id={item.id}
                          title={item.title}
                          busy={busyTaskId !== null}
                          failed={taskMutationError !== null}
                          onSave={onTaskEdit}
                          onClose={() => setEditingId(null)}
                        />
                      )}
                  </View>
                </ShippingListInsert>
              );
            })
          ) : (
            <DesktopEmptyState
              icon={ListChecks}
              error={outcome?.status === 'error'}
              title={
                outcome === null
                  ? 'Gathering your tasks…'
                  : outcome.status === 'error'
                  ? 'Tasks are unavailable'
                  : 'A little room to think.'
              }
              detail={emptyCopy}
            />
          )}
          {taskPagination}
          {outcome?.status === 'success' ? (
            <ReadStatus label="Tasks" mac page={outcome.value.page} />
          ) : null}
        </ScrollView>
      </ScrollFade>
    </View>
  );
}

type AppTileModel = {
  Icon: typeof Puzzle;
  id: string;
  name: string;
  source: string;
  status: string;
};

function cloudAppStatus(app: CloudApp): string {
  if (app.connectedAccounts.length > 0) {
    return 'Connected';
  }
  if (app.enabled) {
    return 'Installed';
  }
  return 'Not connected';
}

function cloudAppSource(app: CloudApp): string {
  if (app.author.length > 0) {
    return app.author;
  }
  if (app.category.length > 0) {
    return app.category;
  }
  return app.description;
}

function tilesFromCatalog(apps: CloudApp[]): AppTileModel[] {
  return apps.map(app => ({
    Icon: Puzzle,
    id: app.id,
    name: app.name,
    source: cloudAppSource(app),
    status: cloudAppStatus(app),
  }));
}

function AppTile({item}: {item: AppTileModel}) {
  const Icon = item.Icon;
  return (
    <View style={styles.appSlot}>
      <View style={styles.appCard}>
        <View style={styles.appIcon}>
          <Icon color={token.color.ink} size={22} />
        </View>
        <Text style={styles.rowTitle}>{item.name}</Text>
        <Text style={styles.rowMeta}>{item.source}</Text>
        <Text style={styles.appStatus}>{item.status}</Text>
      </View>
    </View>
  );
}

export function AppsPage({session}: {session: DesktopSession}) {
  const [section, setSection] = useState<
    'AI assistants' | 'Connect data' | 'Your apps'
  >('Your apps');
  const [tiles, setTiles] = useState<AppTileModel[] | null>();
  useEffect(() => {
    if (session !== 'ready') {
      setTiles(undefined);
      return;
    }
    const backend = omiBackend;
    if (backend === undefined || backend === null) {
      setTiles(null);
      return;
    }
    setTiles(undefined);
    let active = true;
    loadConnectors(backend)
      .then(snapshot => {
        if (!active) {
          return;
        }
        setTiles(tilesFromCatalog(snapshot.apps));
      })
      .catch(() => {
        if (active) {
          setTiles(null);
        }
      });
    return () => {
      active = false;
    };
  }, [session]);
  return (
    <View style={styles.page}>
      <View accessibilityRole="tablist" style={styles.galleryTabs}>
        {(['AI assistants', 'Connect data', 'Your apps'] as const).map(
          label => (
            <FocusPressable
              key={label}
              accessibilityRole="tab"
              accessibilityLabel={label}
              accessibilityState={{selected: section === label}}
              onPress={() => setSection(label)}
              style={[
                styles.galleryTab,
                section === label && styles.galleryTabActive,
              ]}>
              <Text style={styles.rowTitle}>{label}</Text>
            </FocusPressable>
          ),
        )}
      </View>
      <ScrollView contentContainerStyle={styles.galleryContent}>
        <PageHeading
          title={
            section === 'AI assistants'
              ? 'Find your next collaborator.'
              : section === 'Connect data'
              ? 'Bring your world together.'
              : 'Made for your everyday.'
          }
          subtitle={
            section === 'Your apps'
              ? 'Your Omi app catalog and connected accounts.'
              : 'Explore what’s coming to Omi. These integrations are not available yet.'
          }
        />
        <ShippingStage
          stageKey={section}
          variant="hub"
          style={styles.galleryStage}>
          {section !== 'Your apps' ? (
            <ConnectionGallery
              key={section}
              kind={section === 'AI assistants' ? 'agent' : 'context'}
            />
          ) : (
            <View
              style={tiles && tiles.length > 0 ? styles.appGrid : undefined}>
              {tiles === undefined ? (
                <DesktopEmptyState
                  icon={Puzzle}
                  title="Finding your apps…"
                  detail="Loading apps…"
                />
              ) : tiles === null ? (
                <DesktopEmptyState
                  icon={Puzzle}
                  error
                  title="Your apps are out of reach"
                  detail="Apps could not be loaded."
                />
              ) : tiles.length === 0 ? (
                <DesktopEmptyState
                  icon={Puzzle}
                  title="Your collection starts here."
                  detail="No apps are available."
                />
              ) : (
                tiles.map(item => <AppTile item={item} key={item.id} />)
              )}
            </View>
          )}
        </ShippingStage>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  page: {flex: 1, paddingHorizontal: 24, paddingTop: 8},
  libraryRow: {
    paddingHorizontal: 18,
    paddingVertical: 6,
    borderRadius: 14,
    backgroundColor: token.color.glassStrong,
    borderWidth: 1,
    borderColor: token.color.line,
    marginBottom: 8,
  },
  selectedRow: {backgroundColor: token.color.glassSelected},
  galleryStage: {flexBasis: 'auto', flexGrow: 0, flexShrink: 0},
  galleryTabs: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    paddingHorizontal: 0,
    paddingVertical: 8,
  },
  galleryTab: {paddingHorizontal: 14, paddingVertical: 10, borderRadius: 12},
  galleryTabActive: {backgroundColor: token.color.glassSelected},
  galleryContent: {
    paddingVertical: 24,
    maxWidth: 1040,
    width: '100%',
    alignSelf: 'center',
  },
  conversationDetail: {gap: 16, padding: 16},
  memoryDetail: {gap: 16},
  memoryBody: {color: token.color.ink, fontSize: 15, lineHeight: 22},
  backAction: {alignSelf: 'flex-start'},
  taskActions: {flexDirection: 'row', alignItems: 'center', gap: 8},
  taskToggle: {flex: 1, minHeight: 44},
  taskEdit: {
    minWidth: 44,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  hubRow: {
    alignItems: 'center',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 14,
    minHeight: 32,
  },
  hubItem: {
    alignItems: 'center',
    height: 28,
    justifyContent: 'center',
  },
  hubText: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.caption,
    fontWeight: '600',
  },
  hubTextActive: {color: token.color.ink},
  list: {flex: 1},
  listContent: {paddingBottom: 24, paddingTop: 4},
  pageTitle: {
    color: token.color.ink,
    fontFamily: token.font,
    fontSize: token.type.title,
    fontWeight: '600',
  },
  tasksHeader: {alignItems: 'center', flexDirection: 'row', gap: 12},
  searchControl: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    gap: 8,
    height: 32,
  },
  searchInput: {
    color: token.color.ink,
    flex: 1,
    fontFamily: token.font,
    fontSize: token.type.body,
    height: 32,
    minWidth: 0,
    paddingVertical: 0,
  },
  rowTitle: {
    color: token.color.ink,
    fontFamily: token.font,
    fontSize: token.type.title,
    fontWeight: '500',
  },
  rowMeta: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.meta,
    marginTop: 2,
  },
  emptyTitle: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.search,
    fontWeight: '400',
    textAlign: 'center',
  },
  centerState: {
    alignItems: 'center',
    flex: 1,
    gap: 8,
    justifyContent: 'center',
    paddingVertical: 40,
  },
  appGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    paddingHorizontal: 6,
    paddingTop: 12,
  },
  appSlot: {
    padding: 6,
    width: '50%',
    maxWidth: 360,
  },
  appCard: {
    minHeight: 200,
    backgroundColor: token.color.glassStrong,
    borderColor: token.color.line,
    borderWidth: 1,
    borderRadius: 18,
    padding: 22,
  },
  appIcon: {
    alignItems: 'center',
    backgroundColor: token.color.glassStrong,
    borderRadius: 12,
    height: 40,
    justifyContent: 'center',
    marginBottom: 12,
    width: 40,
  },
  appStatus: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.meta,
    marginTop: 12,
  },
});
