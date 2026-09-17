import {FocusPressable as Pressable} from '../ui/Pressable';
import React, {memo, useCallback, useMemo, useState} from 'react';
import {
  FlatList,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {
  TaskEditor,
  TaskMutationStatus,
  type TaskMutationProps,
} from '../ui/TaskEditor';
import House from 'lucide-react-native/icons/house';
import MessageCircle from 'lucide-react-native/icons/message-circle';
import ChevronLeft from 'lucide-react-native/icons/chevron-left';
import Puzzle from 'lucide-react-native/icons/puzzle';
import Settings from 'lucide-react-native/icons/settings';
import Check from 'lucide-react-native/icons/check';
import Pencil from 'lucide-react-native/icons/pencil';
import {OmiAvatar} from '../ui/OmiAvatar';
import {useReduceMotion} from '../app/useReduceMotion';
import type {
  ConversationProjection,
  TaskProjection,
} from '../desktopReadClient';
import {
  mobileColor,
  mobileRadius,
  mobileSpace,
  mobileType,
} from './mobileTokens';

export type MobileProjectionStatus =
  | 'ready'
  | 'loading'
  | 'empty'
  | 'offline'
  | 'error';

export type MobileRoute = 'home' | 'chat' | 'tasks' | 'apps' | 'settings';

export type MobileTask = Pick<
  TaskProjection,
  'id' | 'title' | 'completed' | 'dueAt' | 'owner'
>;

type MobileConversation = Pick<
  ConversationProjection,
  'id' | 'title' | 'summary' | 'createdAt' | 'startedAt'
>;

export type MobileDeviceState = {
  connected: boolean;
  label: string;
};

export type MobileCaptureState = {
  active: boolean;
  waitingForAudio?: boolean;
  transcript: string;
};

export type MobileAppSurfaceProps = TaskMutationProps & {
  taskPagination?: React.ReactNode;
  activeRoute: MobileRoute;
  capture: MobileCaptureState;
  device: MobileDeviceState;
  deviceMessage?: string | null;
  devicePanel?: React.ReactNode;
  settingsContent?: React.ReactNode;
  conversationContent?: React.ReactNode;
  appsContent?: React.ReactNode;
  tasks: readonly MobileTask[];
  taskStatus: MobileProjectionStatus;
  conversations: readonly MobileConversation[];
  conversationStatus: MobileProjectionStatus;
  omnibar: React.ReactNode;
  chatContent?: React.ReactNode;
  searchContent?: React.ReactNode;
  onOpenDevice: () => void;
  onRouteChange: (route: MobileRoute) => void;
  onViewTasks: () => void;
  onViewConversations: () => void;
  onViewMemories: () => void;
};

type DashboardRow =
  | {kind: 'tasks'; key: 'tasks'}
  | {kind: 'conversations'; key: 'conversations'};

const StatePanel = memo(function StatePanel({
  status,
  noun,
}: {
  status: Exclude<MobileProjectionStatus, 'ready'>;
  noun: string;
}) {
  const copy = {
    loading: `Loading ${noun}…`,
    empty: noun === 'tasks' ? "Nothing's waiting on you." : `No ${noun} yet`,
    offline: `Couldn’t refresh ${noun}`,
    error: `Couldn’t load ${noun}`,
  }[status];
  return (
    <View
      accessibilityLabel={`${noun} ${status} state`}
      accessibilityRole={
        status === 'error' || status === 'offline' ? 'alert' : undefined
      }
      style={styles.statePanel}>
      <Text style={styles.stateText}>{copy}</Text>
    </View>
  );
});

const TaskRow = memo(function TaskRow({
  task,
  onToggle,
  onEdit,
  busy,
}: {
  task: MobileTask;
  onToggle?: (id: string) => void;
  onEdit?: (id: string) => void;
  busy: boolean;
}) {
  return (
    <View style={styles.taskRow}>
      <Pressable
        accessibilityLabel={`${
          onToggle
            ? task.completed
              ? 'Reopen'
              : 'Complete'
            : task.completed
            ? 'Completed'
            : 'Open'
        } ${task.title}`}
        accessibilityRole={onToggle ? 'checkbox' : 'text'}
        accessibilityState={{
          checked: task.completed,
          disabled: !onToggle || busy,
          busy,
        }}
        disabled={!onToggle || busy}
        onPress={() => onToggle?.(task.id)}
        style={styles.taskToggle}>
        <View style={[styles.checkbox, task.completed && styles.checkboxDone]}>
          {task.completed && <Check color={mobileColor.background} size={14} />}
        </View>
        <View style={styles.taskCopy}>
          <Text
            style={[styles.taskText, task.completed && styles.taskTextDone]}>
            {task.title}
          </Text>
          {((!task.completed && task.dueAt !== null) || task.owner) && (
            <Text style={styles.taskMeta}>
              {[
                !task.completed && task.dueAt !== null
                  ? `Due ${new Date(task.dueAt).toLocaleDateString(undefined, {
                      month: 'short',
                      day: 'numeric',
                      timeZone: 'UTC',
                    })}`
                  : null,
                task.owner,
              ]
                .filter(Boolean)
                .join(' · ')}
            </Text>
          )}
        </View>
      </Pressable>
      {onEdit && (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Edit ${task.title}`}
          disabled={busy}
          onPress={() => onEdit(task.id)}
          style={styles.taskEdit}>
          <Pencil color={mobileColor.textMuted} size={16} />
        </Pressable>
      )}
    </View>
  );
});

const ConversationRow = memo(function ConversationRow({
  conversation,
}: {
  conversation: MobileConversation;
}) {
  return (
    <View style={styles.conversationRow}>
      <View style={styles.conversationHeading}>
        <Text numberOfLines={2} style={styles.conversationTitle}>
          {conversation.title}
        </Text>
        <Text style={styles.taskMeta}>
          {new Date(
            conversation.startedAt ?? conversation.createdAt,
          ).toLocaleDateString(undefined, {month: 'short', day: 'numeric'})}
        </Text>
      </View>
      {conversation.summary !== '' && (
        <Text numberOfLines={2} style={styles.taskMeta}>
          {conversation.summary}
        </Text>
      )}
    </View>
  );
});

const tabItems = [
  {route: 'home' as const, label: 'Home', Icon: House},
  {route: 'chat' as const, label: 'Conversations', Icon: MessageCircle},
  {route: 'apps' as const, label: 'Apps', Icon: Puzzle},
  {route: 'settings' as const, label: 'Settings', Icon: Settings},
];

function MobileTabBar({
  activeRoute,
  onRouteChange,
}: {
  activeRoute: MobileRoute;
  onRouteChange: (route: MobileRoute) => void;
}) {
  const selectedRoute = activeRoute === 'tasks' ? 'home' : activeRoute;
  return (
    <View accessibilityRole="tablist" style={styles.tabBar}>
      {tabItems.map(({route, label, Icon}) => (
        <Pressable
          accessibilityLabel={label}
          accessibilityRole="tab"
          accessibilityState={{selected: selectedRoute === route}}
          key={route}
          onPress={() => onRouteChange(route)}
          style={[
            styles.tabButton,
            selectedRoute === route && styles.tabActive,
          ]}>
          <View style={styles.tabIcon}>
            <Icon
              color={
                selectedRoute === route
                  ? mobileColor.text
                  : mobileColor.textSubtle
              }
              size={22}
            />
          </View>
          <Text
            style={[
              styles.tabLabel,
              selectedRoute === route && styles.tabLabelActive,
            ]}>
            {label}
          </Text>
        </Pressable>
      ))}
    </View>
  );
}

function SectionHeader({
  action,
  actionLabel,
  title,
}: {
  action: () => void;
  actionLabel: string;
  title: string;
}) {
  return (
    <View style={styles.sectionHeader}>
      <Text style={styles.sectionTitle}>{title}</Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${actionLabel} ${title.toLowerCase()}`}
        onPress={action}
        style={styles.quietButton}>
        <Text style={styles.quietButtonText}>{actionLabel}</Text>
      </Pressable>
    </View>
  );
}

export function MobileAppSurface({
  taskPagination,
  activeRoute,
  omnibar,
  chatContent,
  searchContent,
  capture,
  device,
  deviceMessage,
  devicePanel,
  settingsContent,
  conversationContent,
  appsContent,
  onViewMemories,
  onOpenDevice,
  onRouteChange,
  onTaskToggle,
  onTaskEdit,
  busyTaskId = null,
  taskMutationError = null,
  onRetryTaskMutation,
  onDismissTaskMutation,
  writesAvailable = false,
  onViewConversations,
  onViewTasks,
  conversations,
  conversationStatus,
  tasks,
  taskStatus,
}: MobileAppSurfaceProps): React.JSX.Element {
  const reduceMotion = useReduceMotion();
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const selectedTask = tasks.find(task => task.id === selectedTaskId);
  const openTasks = tasks.filter(task => !task.completed);
  const taskFeedback = useMemo(
    () => (
      <>
        <TaskMutationStatus
          writesAvailable={writesAvailable}
          taskMutationError={taskMutationError}
          onRetryTaskMutation={onRetryTaskMutation}
          onDismissTaskMutation={onDismissTaskMutation}
          busyTaskId={busyTaskId}
        />
        {writesAvailable && onTaskEdit && selectedTask && (
          <TaskEditor
            id={selectedTask.id}
            title={selectedTask.title}
            busy={busyTaskId !== null}
            failed={taskMutationError !== null}
            onSave={onTaskEdit}
            onClose={() => setSelectedTaskId(null)}
          />
        )}
      </>
    ),
    [
      writesAvailable,
      taskMutationError,
      onRetryTaskMutation,
      onDismissTaskMutation,
      busyTaskId,
      onTaskEdit,
      selectedTask,
    ],
  );
  const rows = useMemo<DashboardRow[]>(
    () => [
      {kind: 'tasks', key: 'tasks'},
      {kind: 'conversations', key: 'conversations'},
    ],
    [],
  );

  const renderRow = useCallback(
    ({item}: {item: DashboardRow}) => {
      if (item.kind === 'tasks') {
        return (
          <View style={styles.section}>
            <SectionHeader
              action={onViewTasks}
              actionLabel="See all"
              title="Action items"
            />
            {taskFeedback}
            {taskStatus === 'ready' ? (
              openTasks.length === 0 ? (
                <StatePanel noun="tasks" status="empty" />
              ) : (
                <View>
                  {openTasks.slice(0, 3).map(task => (
                    <TaskRow
                      key={task.id}
                      onToggle={writesAvailable ? onTaskToggle : undefined}
                      onEdit={
                        writesAvailable && onTaskEdit
                          ? setSelectedTaskId
                          : undefined
                      }
                      busy={busyTaskId !== null}
                      task={task}
                    />
                  ))}
                </View>
              )
            ) : (
              <StatePanel noun="tasks" status={taskStatus} />
            )}
          </View>
        );
      }
      return (
        <View style={styles.section}>
          <SectionHeader
            action={onViewConversations}
            actionLabel="See all"
            title="Recent conversations"
          />
          {conversationStatus === 'ready' ? (
            conversations.length === 0 ? (
              <StatePanel noun="conversations" status="empty" />
            ) : (
              conversations
                .slice(0, 3)
                .map(conversation => (
                  <ConversationRow
                    key={conversation.id}
                    conversation={conversation}
                  />
                ))
            )
          ) : (
            <StatePanel noun="conversations" status={conversationStatus} />
          )}
        </View>
      );
    },
    [
      onTaskToggle,
      onTaskEdit,
      writesAvailable,
      busyTaskId,
      taskFeedback,
      onViewConversations,
      onViewTasks,
      conversations,
      conversationStatus,
      openTasks,
      taskStatus,
    ],
  );

  if (activeRoute !== 'home' || chatContent) {
    return (
      <SafeAreaView style={styles.safeArea}>
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={styles.flex}>
          {activeRoute === 'tasks' && !chatContent && (
            <View style={styles.topBar}>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Back to Home"
                onPress={() => onRouteChange('home')}
                style={styles.backButton}>
                <ChevronLeft size={20} color={mobileColor.text} />
                <Text style={styles.quietButtonText}>Home</Text>
              </Pressable>
              <Text style={styles.sectionTitle}>Action items</Text>
            </View>
          )}
          <View style={[styles.flex, styles.stage]}>
            {chatContent ? (
              chatContent
            ) : activeRoute === 'settings' ? (
              <View accessibilityLabel="Settings stage" style={styles.flex}>
                {settingsContent}
              </View>
            ) : activeRoute === 'apps' && appsContent ? (
              <View accessibilityLabel="Connectors stage" style={styles.flex}>
                {appsContent}
              </View>
            ) : activeRoute === 'tasks' ? (
              taskStatus === 'ready' ? (
                <FlatList
                  contentContainerStyle={styles.secondaryList}
                  data={tasks}
                  keyExtractor={task => task.id}
                  ListFooterComponent={<>{taskPagination}</>}
                  ListHeaderComponent={taskFeedback}
                  ListEmptyComponent={
                    <StatePanel noun="tasks" status="empty" />
                  }
                  renderItem={({item}) => (
                    <TaskRow
                      onToggle={writesAvailable ? onTaskToggle : undefined}
                      onEdit={
                        writesAvailable && onTaskEdit
                          ? setSelectedTaskId
                          : undefined
                      }
                      busy={busyTaskId !== null}
                      task={item}
                    />
                  )}
                />
              ) : (
                <View style={[styles.secondaryList, styles.flex]}>
                  <StatePanel noun="tasks" status={taskStatus} />
                  {taskPagination}
                </View>
              )
            ) : activeRoute === 'chat' ? (
              conversationContent ?? (
                <StatePanel noun="conversations" status="error" />
              )
            ) : (
              <View style={styles.secondaryEmpty}>
                <Text style={styles.secondaryPrompt}>
                  No apps connected yet
                </Text>
              </View>
            )}
          </View>
          {omnibar}
          <MobileTabBar
            activeRoute={activeRoute}
            onRouteChange={onRouteChange}
          />
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.flex}>
        <View style={styles.topBar}>
          <View accessibilityLabel="Omi" style={styles.brand}>
            <OmiAvatar
              tone="ink"
              size={28}
              motion="breathe"
              reduceMotion={reduceMotion}
            />
            <Text style={styles.brandText}>omi</Text>
          </View>
          <Pressable
            accessibilityLabel="Open Omi device"
            accessibilityRole="button"
            accessibilityState={{expanded: devicePanel != null}}
            onPress={onOpenDevice}
            style={styles.deviceButton}>
            <View
              style={[
                styles.connectionDot,
                !device.connected && styles.connectionDotOffline,
              ]}
            />
            <Text numberOfLines={1} style={styles.deviceLabel}>
              {device.label}
            </Text>
          </Pressable>
        </View>
        {deviceMessage && (
          <Text accessibilityRole="alert" style={styles.deviceMessage}>
            {deviceMessage}
          </Text>
        )}
        {searchContent ?? (
          <FlatList
            contentContainerStyle={styles.content}
            data={rows}
            ListHeaderComponent={
              devicePanel || capture.active ? (
                <View>
                  {devicePanel}
                  {capture.active && (
                    <Text numberOfLines={2} style={styles.captureStatus}>
                      {capture.waitingForAudio
                        ? 'Waiting for audio'
                        : 'Listening'}
                      {capture.transcript ? ` · ${capture.transcript}` : ''}
                    </Text>
                  )}
                </View>
              ) : null
            }
            ListFooterComponent={
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Saved memories"
                onPress={onViewMemories}
                style={styles.quietButton}>
                <Text style={styles.quietButtonText}>Saved memories</Text>
              </Pressable>
            }
            keyExtractor={item => item.key}
            renderItem={renderRow}
            showsVerticalScrollIndicator={false}
          />
        )}
        {omnibar}
        <MobileTabBar activeRoute={activeRoute} onRouteChange={onRouteChange} />
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  flex: {flex: 1},
  stage: {paddingTop: 12},
  safeArea: {backgroundColor: mobileColor.background, flex: 1},
  brand: {flexDirection: 'row', alignItems: 'center', gap: 8},
  brandText: {fontSize: 24, fontWeight: '600', color: mobileColor.text},
  backButton: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  topBar: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: mobileSpace.sm,
    paddingHorizontal: mobileSpace.md,
    paddingTop: mobileSpace.sm,
  },
  secondaryList: {
    flexGrow: 1,
    paddingBottom: 24,
    paddingHorizontal: mobileSpace.md,
    paddingTop: mobileSpace.sm,
  },
  secondaryEmpty: {
    alignItems: 'center',
    flex: 1,
    justifyContent: 'center',
    padding: mobileSpace.xl,
  },
  secondaryPrompt: {...mobileType.title, color: mobileColor.text},
  secondaryCopy: {
    ...mobileType.body,
    color: mobileColor.textMuted,
    marginTop: mobileSpace.sm,
    textAlign: 'center',
  },
  deviceButton: {
    flexShrink: 1,
    alignItems: 'center',
    backgroundColor: mobileColor.surface,
    borderRadius: mobileRadius.round,
    flexDirection: 'row',
    gap: mobileSpace.sm,
    minHeight: 44,
    paddingHorizontal: mobileSpace.md,
  },
  connectionDot: {
    backgroundColor: mobileColor.connected,
    borderRadius: mobileRadius.round,
    height: 10,
    width: 10,
  },
  connectionDotOffline: {backgroundColor: mobileColor.textSubtle},
  deviceLabel: {
    fontSize: 14,
    lineHeight: 20,
    flexShrink: 1,
    color: mobileColor.text,
    fontWeight: '600',
  },
  deviceMessage: {
    ...mobileType.body,
    color: mobileColor.text,
    padding: mobileSpace.md,
  },
  content: {
    gap: mobileSpace.sm,
    paddingBottom: 12,
    paddingHorizontal: mobileSpace.md,
    paddingTop: mobileSpace.sm,
  },
  captureStatus: {
    ...mobileType.caption,
    color: mobileColor.textMuted,
    paddingVertical: 8,
  },
  section: {
    gap: 0,
    backgroundColor: mobileColor.surface,
    borderColor: mobileColor.border,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: mobileRadius.lg,
    paddingHorizontal: 12,
    paddingVertical: 4,
  },
  sectionHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 2,
  },
  sectionTitle: {
    flexShrink: 1,
    fontSize: 18,
    lineHeight: 24,
    fontWeight: '600',
    color: mobileColor.text,
  },
  quietButton: {
    borderRadius: mobileRadius.round,
    minHeight: 44,
    justifyContent: 'center',
    paddingHorizontal: mobileSpace.sm,
    paddingVertical: mobileSpace.sm,
  },
  quietButtonText: {...mobileType.caption, color: mobileColor.textMuted},
  taskRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: mobileSpace.sm,
    minHeight: 64,
    paddingVertical: mobileSpace.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: mobileColor.border,
  },
  taskToggle: {
    flex: 1,
    minHeight: 44,
    flexDirection: 'row',
    gap: 12,
    alignItems: 'center',
  },
  taskEdit: {
    minHeight: 44,
    minWidth: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkbox: {
    borderColor: mobileColor.textSubtle,
    borderRadius: mobileRadius.round,
    borderWidth: 1.5,
    height: 22,
    width: 22,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkboxDone: {backgroundColor: mobileColor.textSubtle},
  taskCopy: {flex: 1, gap: 3},
  taskText: {fontSize: 15, lineHeight: 22, color: mobileColor.text},
  taskMeta: {fontSize: 12, lineHeight: 18, color: mobileColor.textMuted},
  taskTextDone: {
    color: mobileColor.textSubtle,
    textDecorationLine: 'line-through',
  },
  conversationRow: {
    paddingVertical: 12,
    gap: 5,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: mobileColor.border,
  },
  conversationHeading: {flexDirection: 'row', alignItems: 'baseline', gap: 12},
  conversationTitle: {
    flex: 1,
    fontSize: 15,
    lineHeight: 22,
    fontWeight: '500',
    color: mobileColor.text,
  },
  statePanel: {
    minHeight: 44,
    justifyContent: 'center',
    paddingVertical: 8,
  },
  stateText: {
    ...mobileType.body,
    color: mobileColor.textMuted,
  },
  tabBar: {
    alignItems: 'center',
    backgroundColor: mobileColor.surfaceQuiet,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: mobileColor.border,
    borderRadius: mobileRadius.lg,
    marginHorizontal: 10,
    marginBottom: 8,
    flexDirection: 'row',
    minHeight: 68,
    flexShrink: 0,
    justifyContent: 'space-around',
    padding: 4,
    gap: 2,
  },
  tabButton: {
    alignItems: 'center',
    flex: 1,
    justifyContent: 'center',
    minHeight: 60,
    gap: 3,
    borderRadius: 18,
  },
  tabIcon: {paddingVertical: 4},
  tabActive: {backgroundColor: mobileColor.surfaceRaised},
  tabLabel: {fontSize: 10, color: mobileColor.textSubtle},
  tabLabelActive: {color: mobileColor.text},
  tabGlyph: {color: mobileColor.textSubtle, fontSize: 30},
  tabGlyphActive: {color: mobileColor.text},
});
