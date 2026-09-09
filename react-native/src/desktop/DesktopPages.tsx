import React, {useCallback, useEffect, useState} from 'react';
import {ScrollView, StyleSheet, Text, View} from 'react-native';
import Puzzle from 'lucide-react-native/icons/puzzle';
import {
  cloudErrorCanRetry,
  disableCloudApp,
  enableCloudApp,
  loadConnectors,
  type CloudApp,
} from '../desktopCloudClient';
import {
  appDisplayName,
  appDisplaySource,
  desktopAppsUnavailableCopy,
  desktopBackendUnavailableCopy,
  desktopReadErrorCopy,
  taskDisplayTitle,
  conversationRecapTitle,
  visibleDisplayText,
  type DesktopReadOutcomes,
} from '../desktopReadClient';
import {omiBackend} from '../omiNative';
import {ConversationDetail} from '../ui/ConversationDetail';
import {ReadStatus, emptyLibraryCopy} from '../ui/ReadStatus';
import {FocusPressable} from '../ui/Pressable';
import {
  TaskEditor,
  TaskMutationStatus,
  type TaskMutationProps,
} from '../ui/TaskEditor';
import {ShippingListInsert} from './ShippingStage';
import {ConversationRow, EmptyCopy, TaskRow} from './DesktopRows';
import type {DesktopSession} from './desktopChrome';
import {desktopTokens as token} from './tokens';

export function LibraryPage({
  conversationNotice = null,
  conversationsLoadingMore = false,
  onLoadMoreConversations,
  onRequestedConversationConsumed,
  outcomes,
  requestedConversationId = null,
}: {
  conversationNotice?: string | null;
  conversationsLoadingMore?: boolean;
  onLoadMoreConversations?: () => void;
  onRequestedConversationConsumed?: () => void;
  outcomes: DesktopReadOutcomes | null;
  requestedConversationId?: string | null;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const outcome = outcomes?.conversations ?? null;
  const conversations =
    outcome?.status === 'success' ? outcome.value.items : [];
  const selected = conversations.find(item => item.id === selectedId) ?? null;
  useEffect(() => {
    if (requestedConversationId === null) {
      return;
    }
    setSelectedId(requestedConversationId);
    onRequestedConversationConsumed?.();
  }, [onRequestedConversationConsumed, requestedConversationId]);
  useEffect(() => {
    if (selectedId !== null && selected === null) {
      setSelectedId(null);
    }
  }, [selected, selectedId]);
  // A failed or unsettled read must never claim "nothing captured": only a
  // successful empty page is an empty library.
  const emptyCopy =
    outcome === null
      ? 'Loading conversations…'
      : outcome.status === 'error'
      ? outcome.error
      : emptyLibraryCopy(
          'Conversations',
          outcome.value.page,
          false,
          'Nothing captured in this window yet.',
          'Nothing captured in this window yet.',
        );
  return (
    <View style={styles.page}>
      {selected !== null ? (
        <ScrollView
          accessibilityLabel="Selected conversation details"
          contentContainerStyle={styles.listContent}
          style={styles.list}>
          <FocusPressable
            accessibilityLabel="Back to conversations"
            accessibilityRole="button"
            onPress={() => setSelectedId(null)}
            style={[styles.taskEdit, styles.backAction]}>
            <Text style={styles.rowMeta}>Back to conversations</Text>
          </FocusPressable>
          <ConversationDetail
            apiContract={
              outcome?.status === 'success'
                ? outcome.value.apiContract
                : undefined
            }
            conversation={selected}
            desktop
          />
        </ScrollView>
      ) : (
        <ScrollView
          contentContainerStyle={styles.listContent}
          style={styles.list}>
          {conversations.length > 0 ? (
            conversations.map(item => (
              <ShippingListInsert itemKey={item.id} key={item.id}>
                <FocusPressable
                  accessibilityLabel={`Open conversation ${conversationRecapTitle(
                    item,
                  )}`}
                  accessibilityRole="button"
                  onPress={() => setSelectedId(item.id)}
                  style={styles.pageAction}>
                  <ConversationRow item={item} />
                </FocusPressable>
              </ShippingListInsert>
            ))
          ) : (
            <EmptyCopy>{emptyCopy}</EmptyCopy>
          )}
          {conversationNotice !== null ? (
            <Text accessibilityRole="alert" style={styles.rowMeta}>
              {conversationNotice}
            </Text>
          ) : null}
          {outcome?.status === 'success' &&
          outcome.value.page.hasMore &&
          onLoadMoreConversations ? (
            <FocusPressable
              accessibilityLabel="Load more conversations"
              accessibilityRole="button"
              disabled={conversationsLoadingMore}
              onPress={onLoadMoreConversations}
              style={styles.pageAction}>
              <Text style={styles.rowMeta}>
                {conversationsLoadingMore
                  ? 'Loading…'
                  : 'Load more conversations'}
              </Text>
            </FocusPressable>
          ) : null}
          {outcome?.status === 'success' && conversations.length > 0 ? (
            <ReadStatus
              continueUnavailable={
                conversationNotice === desktopBackendUnavailableCopy
              }
              label="Conversations"
              mac
              page={outcome.value.page}
            />
          ) : null}
        </ScrollView>
      )}
    </View>
  );
}

export function TasksPage({
  outcomes,
  taskPagination,
  taskNotice = null,
  onTaskToggle,
  onTaskEdit,
  busyTaskId = null,
  writesAvailable,
  taskMutationError = null,
  onRetryTaskMutation,
  onDismissTaskMutation,
}: TaskMutationProps & {
  outcomes: DesktopReadOutcomes | null;
  taskPagination?: React.ReactNode;
  taskNotice?: string | null;
}) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const outcome = outcomes?.tasks ?? null;
  const tasks = outcome?.status === 'success' ? outcome.value.items : [];
  const emptyCopy =
    outcome === null
      ? 'Loading tasks…'
      : outcome.status === 'error'
      ? outcome.error
      : emptyLibraryCopy(
          'Tasks',
          outcome.value.page,
          false,
          'No tasks yet',
          'No tasks yet',
        );
  return (
    <View style={styles.page}>
      <TaskMutationStatus
        writesAvailable={writesAvailable}
        taskMutationError={taskMutationError}
        onRetryTaskMutation={onRetryTaskMutation}
        onDismissTaskMutation={onDismissTaskMutation}
      />
      <ScrollView
        contentContainerStyle={styles.listContent}
        style={styles.list}>
        {tasks.length > 0 ? (
          tasks.map(item => {
            const editable =
              outcome?.status === 'success' &&
              (outcome.value.apiContract === 'omi' || item.revision !== null);
            return (
              <ShippingListInsert itemKey={item.id} key={item.id}>
                <View style={styles.taskActions}>
                  <FocusPressable
                    accessibilityRole={
                      writesAvailable && onTaskToggle ? 'checkbox' : 'text'
                    }
                    accessibilityLabel={
                      writesAvailable
                        ? `${
                            item.completed ? 'Reopen' : 'Complete'
                          } task: ${taskDisplayTitle(item)}`
                        : item.completed
                        ? `Completed task: ${taskDisplayTitle(item)}`
                        : `Task: ${taskDisplayTitle(item)}`
                    }
                    accessibilityState={{
                      checked: item.completed,
                      disabled:
                        !writesAvailable ||
                        !onTaskToggle ||
                        !editable ||
                        busyTaskId !== null,
                      busy:
                        busyTaskId === item.id && taskMutationError === null,
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
                      accessibilityLabel={`Edit task: ${taskDisplayTitle(
                        item,
                      )}`}
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
                      id={item.id}
                      title={item.title.trim()}
                      busy={busyTaskId !== null}
                      failed={taskMutationError !== null}
                      onSave={onTaskEdit}
                      onClose={() => setEditingId(null)}
                    />
                  )}
              </ShippingListInsert>
            );
          })
        ) : (
          <EmptyCopy>{emptyCopy}</EmptyCopy>
        )}
        {taskPagination}
        {outcome?.status === 'success' && tasks.length > 0 ? (
          <ReadStatus
            continueUnavailable={taskNotice === desktopBackendUnavailableCopy}
            label="Tasks"
            mac
            page={outcome.value.page}
          />
        ) : null}
      </ScrollView>
    </View>
  );
}

type AppTileModel = {
  Icon: typeof Puzzle;
  id: string;
  name: string;
  description: string;
  source: string;
  status: string;
  enabled: boolean;
};

function cloudAppStatus(app: CloudApp, installKnown: boolean): string {
  if (app.connectedAccounts.length > 0) {
    return 'Connected';
  }
  if (!installKnown) {
    return '';
  }
  if (app.enabled) {
    return 'Installed';
  }
  return 'Not connected';
}

function tilesFromCatalog(
  apps: CloudApp[],
  installKnown: boolean,
): AppTileModel[] {
  return apps.map(app => ({
    Icon: Puzzle,
    id: app.id,
    name: appDisplayName(app.name),
    description: visibleDisplayText(app.description),
    source: appDisplaySource(app),
    status: cloudAppStatus(app, installKnown),
    enabled: app.enabled,
  }));
}

function AppTile({
  busy,
  item,
  pending,
  onToggle,
}: {
  busy: boolean;
  item: AppTileModel;
  pending: boolean;
  onToggle?: (id: string, enabled: boolean) => void;
}) {
  const Icon = item.Icon;
  return (
    <View style={styles.appSlot}>
      <View style={styles.appCard}>
        <View style={styles.appIcon}>
          <Icon color={token.color.ink} size={22} />
        </View>
        <Text style={styles.rowTitle}>{item.name}</Text>
        {item.description !== '' ? (
          <Text numberOfLines={2} style={styles.rowMeta}>
            {item.description}
          </Text>
        ) : null}
        {item.source !== '' && item.source !== item.description ? (
          <Text style={styles.rowMeta}>{item.source}</Text>
        ) : null}
        {item.status.length > 0 ? (
          <Text style={styles.appStatus}>{item.status}</Text>
        ) : null}
        {onToggle ? (
          <FocusPressable
            accessibilityLabel={
              item.enabled ? `Remove ${item.name}` : `Install ${item.name}`
            }
            accessibilityRole="button"
            accessibilityState={{disabled: busy}}
            disabled={busy}
            onPress={() => onToggle(item.id, !item.enabled)}
            style={styles.appAction}>
            <Text style={styles.rowMeta}>
              {pending
                ? item.enabled
                  ? 'Removing…'
                  : 'Installing…'
                : item.enabled
                ? 'Remove'
                : 'Install'}
            </Text>
          </FocusPressable>
        ) : null}
      </View>
    </View>
  );
}

export function AppsPage({session}: {session: DesktopSession}) {
  const [tiles, setTiles] = useState<AppTileModel[] | null>();
  const [enabledError, setEnabledError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [installKnown, setInstallKnown] = useState(false);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [writesAvailable, setWritesAvailable] = useState(true);
  const reload = useCallback(async () => {
    const backend = omiBackend;
    if (session !== 'ready' || backend === undefined || backend === null) {
      return;
    }
    const snapshot = await loadConnectors(backend);
    setTiles(tilesFromCatalog(snapshot.apps, snapshot.enabledIds !== null));
    setEnabledError(snapshot.enabledError);
    setInstallKnown(snapshot.enabledIds !== null);
    setError(null);
  }, [session]);
  useEffect(() => {
    let active = true;
    if (session !== 'ready') {
      setTiles(undefined);
      setEnabledError(null);
      setError(null);
      setInstallKnown(false);
      setPendingId(null);
      setActionError(null);
      setWritesAvailable(true);
      return () => {
        active = false;
      };
    }
    const backend = omiBackend;
    if (backend === undefined || backend === null) {
      setTiles(null);
      setEnabledError(null);
      setError(null);
      setInstallKnown(false);
      return () => {
        active = false;
      };
    }
    setTiles(undefined);
    setEnabledError(null);
    setError(null);
    setInstallKnown(false);
    reload().catch(reason => {
      if (active) {
        setTiles(null);
        setEnabledError(null);
        setError(desktopReadErrorCopy(reason));
        setInstallKnown(false);
      }
    });
    return () => {
      active = false;
    };
  }, [reload, session]);
  const setEnabled = async (id: string, enabled: boolean) => {
    const backend = omiBackend;
    if (backend === undefined || backend === null || pendingId !== null) {
      return;
    }
    setPendingId(id);
    setActionError(null);
    try {
      if (enabled) {
        await enableCloudApp(backend, id);
      } else {
        await disableCloudApp(backend, id);
      }
      await reload();
    } catch (reason) {
      setActionError(desktopReadErrorCopy(reason));
      if (!cloudErrorCanRetry(reason)) {
        setWritesAvailable(false);
      }
    } finally {
      setPendingId(null);
    }
  };
  return (
    <View style={styles.page}>
      <ScrollView contentContainerStyle={styles.appGrid}>
        {tiles === undefined ? (
          <EmptyCopy>Loading apps…</EmptyCopy>
        ) : tiles === null ? (
          <EmptyCopy>
            {error === desktopAppsUnavailableCopy
              ? desktopAppsUnavailableCopy
              : 'Apps could not be loaded.'}
          </EmptyCopy>
        ) : (
          <>
            {enabledError !== null ? (
              <EmptyCopy>{enabledError}</EmptyCopy>
            ) : null}
            {actionError !== null ? (
              <Text accessibilityRole="alert" style={styles.rowMeta}>
                {actionError}
              </Text>
            ) : null}
            {tiles.length === 0 ? (
              enabledError === null ? (
                <EmptyCopy>No apps are available.</EmptyCopy>
              ) : null
            ) : (
              tiles.map(item => (
                <AppTile
                  busy={pendingId !== null}
                  item={item}
                  key={item.id}
                  onToggle={
                    writesAvailable && installKnown ? setEnabled : undefined
                  }
                  pending={pendingId === item.id}
                />
              ))
            )}
          </>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  page: {flex: 1},
  pageAction: {minHeight: 44, justifyContent: 'center'},
  taskActions: {flexDirection: 'row', alignItems: 'center', gap: 8},
  taskToggle: {flex: 1, minHeight: 44},
  taskEdit: {
    minWidth: 44,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  backAction: {alignSelf: 'flex-start'},
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
  },
  appCard: {
    aspectRatio: 1,
    backgroundColor: token.color.glassQuiet,
    borderRadius: 16,
    padding: 12,
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
  appAction: {minHeight: 44, justifyContent: 'center'},
});
