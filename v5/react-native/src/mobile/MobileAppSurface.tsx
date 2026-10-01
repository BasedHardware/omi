import {FocusPressable as Pressable} from '../ui/Pressable';
import React, {
  memo,
  useCallback,
  useId,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  FlatList,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import Svg, {Defs, LinearGradient, Rect, Stop} from 'react-native-svg';
import {
  TaskEditor,
  TaskMutationStatus,
  type TaskMutationProps,
} from '../ui/TaskEditor';
import {MaterialIcon, type MaterialIconName} from '../ui/MaterialIcon';

import {OmiAvatar} from '../ui/OmiAvatar';
import {useReduceMotion} from '../app/useReduceMotion';
import type {
  ConversationProjection,
  TaskProjection,
} from '../desktopReadClient';
import {useOmiStyles, useOmiTheme} from '../design/OmiTheme';
import {markInk} from './MobileTheme';
import {OmiPageState} from '../design/primitives';
import type {OmiTheme} from '../design/tokens';
import {
  MobileGroup,
  MobileInlineState,
  MobileRow,
  MobileSectionHeader,
  TaskMark,
} from './MobileList';
import {epochOf, mobileWhenLabel} from './mobileDates';

function ContentEdges({children}: {children: React.ReactNode}) {
  const id = useId();
  const theme = useOmiTheme();
  const styles = useOmiStyles(createStyles);
  return (
    <View style={styles.flex}>
      {children}
      {(['top', 'bottom'] as const).map(edge => (
        <Svg
          key={edge}
          pointerEvents="none"
          accessible={false}
          width="100%"
          height={24}
          style={[styles.edgeFade, {[edge]: 0}]}>
          <Defs>
            <LinearGradient id={`${id}-${edge}`} x1="0" y1="0" x2="0" y2="1">
              <Stop
                offset="0"
                stopColor={theme.color.canvas}
                stopOpacity={edge === 'top' ? 1 : 0}
              />
              <Stop
                offset="1"
                stopColor={theme.color.canvas}
                stopOpacity={edge === 'top' ? 0 : 1}
              />
            </LinearGradient>
          </Defs>
          <Rect width="100%" height="100%" fill={`url(#${id}-${edge})`} />
        </Svg>
      ))}
    </View>
  );
}

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
  /** Re-reads the account projections after a failed read (Try Again). */
  onRetryReads?: () => void;
};

type DashboardRow =
  | {kind: 'tasks'; key: 'tasks'}
  | {kind: 'conversations'; key: 'conversations'};

/** Home's inline section state: honest about loading and failed reads. */
const SectionState = memo(function SectionState({
  status,
  noun,
}: {
  status: Exclude<MobileProjectionStatus, 'ready'>;
  noun: string;
}) {
  const copy = {
    loading: `Loading ${noun}…`,
    empty: noun === 'tasks' ? "Nothing's waiting on you." : `No ${noun} yet.`,
    offline: `Couldn’t refresh ${noun}`,
    error: `Couldn’t load ${noun}`,
  }[status];
  return (
    <MobileInlineState
      accessibilityLabel={`${noun} ${status} state`}
      label={copy}
      tone={status === 'error' || status === 'offline' ? 'alert' : 'quiet'}
    />
  );
});

function formatDue(dueAt: number): string {
  return `Due ${new Date(dueAt).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })}`;
}

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
  const theme = useOmiTheme();
  const styles = useOmiStyles(createStyles);
  const meta = [
    !task.completed && task.dueAt !== null ? formatDue(task.dueAt) : null,
    task.owner,
  ]
    .filter(Boolean)
    .join(' · ');
  return (
    <MobileRow
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
      leading={<TaskMark done={task.completed} />}
      title={task.title}
      titleStyle={task.completed ? 'done' : 'default'}
      subtitle={meta === '' ? null : meta}
      trailing={
        onEdit ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Edit ${task.title}`}
            disabled={busy}
            onPress={() => onEdit(task.id)}
            style={styles.rowAction}>
            <MaterialIcon
              name="edit"
              color={theme.color.inkTertiary}
              size={theme.size.iconSmall}
            />
          </Pressable>
        ) : undefined
      }
    />
  );
});

const ConversationRow = memo(function ConversationRow({
  conversation,
  nowMs,
}: {
  conversation: MobileConversation;
  nowMs: number;
}) {
  return (
    <MobileRow
      title={conversation.title || 'Untitled conversation'}
      titleStyle={conversation.title ? 'default' : 'placeholder'}
      titleLines={1}
      trailingText={mobileWhenLabel(
        epochOf(conversation.startedAt ?? conversation.createdAt),
        nowMs,
      )}
      subtitle={conversation.summary === '' ? null : conversation.summary}
    />
  );
});

const tabItems: Array<{
  route: MobileRoute;
  label: string;
  icon: MaterialIconName;
}> = [
  {route: 'home', label: 'Home', icon: 'home'},
  {route: 'chat', label: 'Conversations', icon: 'forum'},
  {route: 'tasks', label: 'Tasks', icon: 'checklist'},
  {route: 'settings', label: 'Settings', icon: 'settings'},
];

/**
 * Four icon destinations, like the shipping phone app: selected is ink,
 * unselected is tertiary ink, no pill slab. The label is the accessible name
 * (and the web tooltip).
 */
function MobileTabBar({
  activeRoute,
  onRouteChange,
}: {
  activeRoute: MobileRoute;
  onRouteChange: (route: MobileRoute) => void;
}) {
  const theme = useOmiTheme();
  const styles = useOmiStyles(createStyles);
  const selectedRoute = activeRoute === 'apps' ? 'settings' : activeRoute;
  return (
    <View accessibilityRole="tablist" style={styles.tabBar}>
      {tabItems.map(({route, label, icon}) => (
        <Pressable
          accessibilityLabel={label}
          accessibilityRole="tab"
          accessibilityState={{selected: selectedRoute === route}}
          key={route}
          onPress={() => onRouteChange(route)}
          {...({title: label} as object)}
          style={({pressed}) => [styles.tabButton, pressed && styles.pressed]}>
          <MaterialIcon
            color={
              selectedRoute === route
                ? theme.color.ink
                : theme.color.inkTertiary
            }
            name={icon}
            size={26}
          />
        </Pressable>
      ))}
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
  onRetryReads,
  conversations,
  conversationStatus,
  tasks,
  taskStatus,
}: MobileAppSurfaceProps): React.JSX.Element {
  const reduceMotion = useReduceMotion();
  const theme = useOmiTheme();
  const styles = useOmiStyles(createStyles);
  const nowMs = useRef(Date.now()).current;
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const selectedTask = tasks.find(task => task.id === selectedTaskId);
  const openTasks = useMemo(
    () => tasks.filter(task => !task.completed),
    [tasks],
  );
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
  const renderTask = useCallback(
    (task: MobileTask) => (
      <TaskRow
        key={task.id}
        onToggle={writesAvailable ? onTaskToggle : undefined}
        onEdit={writesAvailable && onTaskEdit ? setSelectedTaskId : undefined}
        busy={busyTaskId !== null}
        task={task}
      />
    ),
    [writesAvailable, onTaskToggle, onTaskEdit, busyTaskId],
  );

  const renderRow = useCallback(
    ({item}: {item: DashboardRow}) => {
      if (item.kind === 'tasks') {
        return (
          <View style={styles.section}>
            <MobileSectionHeader
              title="Tasks"
              action={{
                label: 'See All',
                accessibilityLabel: 'See all tasks',
                onPress: onViewTasks,
              }}
            />
            {taskFeedback}
            <MobileGroup inset={52}>
              {taskStatus === 'ready' ? (
                openTasks.length === 0 ? (
                  <SectionState noun="tasks" status="empty" />
                ) : (
                  openTasks.slice(0, 3).map(renderTask)
                )
              ) : (
                <SectionState noun="tasks" status={taskStatus} />
              )}
            </MobileGroup>
          </View>
        );
      }
      return (
        <View style={styles.section}>
          <MobileSectionHeader
            title="Recent Conversations"
            action={{
              label: 'See All',
              accessibilityLabel: 'See all conversations',
              onPress: onViewConversations,
            }}
          />
          <MobileGroup>
            {conversationStatus === 'ready' ? (
              conversations.length === 0 ? (
                <SectionState noun="conversations" status="empty" />
              ) : (
                conversations
                  .slice(0, 3)
                  .map(conversation => (
                    <ConversationRow
                      key={conversation.id}
                      conversation={conversation}
                      nowMs={nowMs}
                    />
                  ))
              )
            ) : (
              <SectionState noun="conversations" status={conversationStatus} />
            )}
          </MobileGroup>
        </View>
      );
    },
    [
      styles,
      renderTask,
      taskFeedback,
      onViewConversations,
      onViewTasks,
      conversations,
      conversationStatus,
      openTasks,
      taskStatus,
      nowMs,
    ],
  );

  if (activeRoute !== 'home' || chatContent) {
    return (
      <SafeAreaView style={styles.safeArea}>
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={styles.flex}>
          {activeRoute === 'apps' && !chatContent && (
            <View style={styles.navBar}>
              <Text
                accessibilityRole="header"
                numberOfLines={1}
                style={styles.navTitle}>
                Apps
              </Text>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Back to Settings"
                onPress={() => onRouteChange('settings')}
                style={({pressed}) => [
                  styles.backButton,
                  pressed && styles.pressed,
                ]}>
                <MaterialIcon
                  name="chevron_left"
                  size={theme.size.icon + 4}
                  color={theme.color.ink}
                />
                <Text style={styles.backText}>Settings</Text>
              </Pressable>
            </View>
          )}
          <View style={[styles.flex, !chatContent && styles.stage]}>
            <ContentEdges>
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
                  <TaskList
                    tasks={tasks}
                    header={taskFeedback}
                    footer={taskPagination}
                    renderTask={renderTask}
                  />
                ) : (
                  <View
                    accessibilityLabel={`tasks ${taskStatus} state`}
                    style={[styles.pageList, styles.flex]}>
                    {taskStatus === 'loading' ? (
                      <OmiPageState kind="loading" label="Loading tasks…" />
                    ) : taskStatus === 'empty' ? (
                      <OmiPageState
                        kind="empty"
                        icon="checklist"
                        title="No Tasks"
                        message="Nothing's waiting on you."
                      />
                    ) : (
                      <OmiPageState
                        kind="error"
                        title={
                          taskStatus === 'offline'
                            ? 'Couldn’t Refresh Tasks'
                            : 'Couldn’t Load Tasks'
                        }
                        onRetry={onRetryReads}
                      />
                    )}
                    {taskPagination}
                  </View>
                )
              ) : activeRoute === 'chat' ? (
                conversationContent ?? (
                  <OmiPageState
                    kind="error"
                    title="Couldn’t Load Conversations"
                    onRetry={onRetryReads}
                  />
                )
              ) : (
                <OmiPageState
                  kind="empty"
                  icon="extension"
                  title="No Apps Yet"
                  message="Apps you connect to Omi will appear here."
                />
              )}
            </ContentEdges>
          </View>
          {omnibar}
          {!chatContent && (
            <MobileTabBar
              activeRoute={activeRoute}
              onRouteChange={onRouteChange}
            />
          )}
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
              size={24}
              motion="breathe"
              inkColor={markInk(theme)}
              reduceMotion={reduceMotion}
            />
            <Text style={styles.brandText}>omi</Text>
          </View>
          <Pressable
            accessibilityLabel="Open Omi device"
            accessibilityRole="button"
            accessibilityState={{expanded: devicePanel != null}}
            onPress={onOpenDevice}
            style={({pressed}) => [
              styles.deviceButton,
              pressed && styles.devicePressed,
            ]}>
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
          <View style={styles.notice}>
            <Text accessibilityRole="alert" style={styles.noticeText}>
              {deviceMessage}
            </Text>
          </View>
        )}
        <ContentEdges>
          {searchContent ?? (
            <FlatList
              contentContainerStyle={styles.content}
              data={rows}
              ListHeaderComponent={
                devicePanel || capture.active ? (
                  <View style={styles.homeHeader}>
                    {devicePanel}
                    {capture.active && (
                      <View style={styles.capture}>
                        <View
                          style={[
                            styles.captureDot,
                            capture.waitingForAudio && styles.captureDotWaiting,
                          ]}
                        />
                        <Text numberOfLines={2} style={styles.captureStatus}>
                          {capture.waitingForAudio
                            ? 'Waiting for audio'
                            : 'Listening'}
                          {capture.transcript ? ` · ${capture.transcript}` : ''}
                        </Text>
                      </View>
                    )}
                  </View>
                ) : null
              }
              keyExtractor={item => item.key}
              renderItem={renderRow}
              showsVerticalScrollIndicator={false}
            />
          )}
        </ContentEdges>
        {omnibar}
        <MobileTabBar activeRoute={activeRoute} onRouteChange={onRouteChange} />
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

type TaskListRow =
  | {kind: 'label'; key: string; label: string}
  | {
      kind: 'task';
      key: string;
      task: MobileTask;
      first: boolean;
      last: boolean;
    };

/** The Tasks tab: To Do then Done, each one grouped surface. */
function TaskList({
  tasks,
  header,
  footer,
  renderTask,
}: {
  tasks: readonly MobileTask[];
  header: React.ReactElement;
  footer: React.ReactNode;
  renderTask: (task: MobileTask) => React.ReactNode;
}) {
  const styles = useOmiStyles(createStyles);
  const data = useMemo<TaskListRow[]>(() => {
    const rowsFor = (label: string, items: MobileTask[]): TaskListRow[] =>
      items.length === 0
        ? []
        : [
            {kind: 'label', key: `label:${label}`, label},
            ...items.map((task, index) => ({
              kind: 'task' as const,
              key: task.id,
              task,
              first: index === 0,
              last: index === items.length - 1,
            })),
          ];
    return [
      ...rowsFor(
        'To Do',
        tasks.filter(task => !task.completed),
      ),
      ...rowsFor(
        'Done',
        tasks.filter(task => task.completed),
      ),
    ];
  }, [tasks]);
  return (
    <FlatList
      contentContainerStyle={styles.pageList}
      data={data}
      keyExtractor={row => row.key}
      ListFooterComponent={<>{footer}</>}
      ListHeaderComponent={header}
      ListEmptyComponent={
        <View accessibilityLabel="tasks empty state">
          <OmiPageState
            kind="empty"
            icon="checklist"
            title="No Tasks"
            message="Nothing's waiting on you."
          />
        </View>
      }
      renderItem={({item}) =>
        item.kind === 'label' ? (
          <MobileSectionHeader title={item.label} />
        ) : (
          <View
            style={[
              styles.listCell,
              item.first && styles.listCellFirst,
              item.last && styles.listCellLast,
            ]}>
            {item.first ? null : <View style={styles.listSeparator} />}
            {renderTask(item.task)}
          </View>
        )
      }
    />
  );
}

const createStyles = (t: OmiTheme) => ({
  flex: {flex: 1},
  edgeFade: {position: 'absolute' as const, left: 0},
  stage: {paddingTop: t.space.xs},
  safeArea: {backgroundColor: t.color.canvas, flex: 1},
  pressed: {opacity: t.motion.pressedOpacity},
  brand: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: t.space.sm,
    flexShrink: 0,
  },
  brandText: {
    ...t.type.title,
    color: t.color.ink,
  },
  topBar: {
    alignItems: 'center' as const,
    flexDirection: 'row' as const,
    justifyContent: 'space-between' as const,
    gap: t.space.md,
    minHeight: 52,
    paddingHorizontal: t.layout.pageGutter.mobile,
    paddingTop: t.space.xs,
  },
  navBar: {
    minHeight: t.size.hitTarget + t.space.xs,
    justifyContent: 'center' as const,
    paddingHorizontal: t.space.sm,
  },
  navTitle: {
    ...t.type.headline,
    color: t.color.ink,
    position: 'absolute' as const,
    left: 96,
    right: 96,
    textAlign: 'center' as const,
  },
  backButton: {
    alignSelf: 'flex-start' as const,
    minHeight: t.size.hitTarget,
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    paddingRight: t.space.sm,
  },
  backText: {...t.type.body, color: t.color.ink},
  deviceButton: {
    flexShrink: 1,
    minWidth: 0,
    alignItems: 'center' as const,
    backgroundColor: t.color.surface,
    borderRadius: t.radius.pill,
    flexDirection: 'row' as const,
    gap: t.space.sm,
    minHeight: t.size.hitTarget,
    paddingHorizontal: t.space.lg,
  },
  devicePressed: {backgroundColor: t.color.surfaceRaised},
  connectionDot: {
    backgroundColor: t.color.live,
    borderRadius: 4,
    height: 8,
    width: 8,
  },
  connectionDotOffline: {backgroundColor: t.color.inkTertiary},
  deviceLabel: {
    ...t.type.subhead,
    fontWeight: '600' as const,
    flexShrink: 1,
    color: t.color.ink,
  },
  notice: {
    marginHorizontal: t.layout.pageGutter.mobile,
    marginTop: t.space.sm,
    padding: t.space.md,
    borderRadius: t.radius.row,
    backgroundColor: t.color.surface,
  },
  noticeText: {...t.type.subhead, color: t.color.ink},
  content: {
    gap: t.space.lg,
    paddingBottom: t.space.xxl,
    paddingHorizontal: t.layout.pageGutter.mobile,
    paddingTop: t.space.sm,
  },
  homeHeader: {gap: t.space.md},
  capture: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: t.space.sm,
    paddingHorizontal: t.space.xs,
  },
  captureDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: t.color.live,
  },
  captureDotWaiting: {backgroundColor: t.color.warning},
  captureStatus: {
    ...t.type.footnote,
    color: t.color.inkSecondary,
    flexShrink: 1,
  },
  section: {gap: t.space.xs},
  rowAction: {
    minHeight: t.size.hitTarget,
    minWidth: t.size.hitTarget,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
  },
  pageList: {
    flexGrow: 1,
    paddingBottom: t.space.xxl,
    paddingHorizontal: t.layout.pageGutter.mobile,
    paddingTop: t.space.xs,
  },
  listCell: {backgroundColor: t.color.surface},
  listCellFirst: {
    borderTopLeftRadius: t.radius.card,
    borderTopRightRadius: t.radius.card,
    overflow: 'hidden' as const,
  },
  listCellLast: {
    borderBottomLeftRadius: t.radius.card,
    borderBottomRightRadius: t.radius.card,
    marginBottom: t.space.sm,
    overflow: 'hidden' as const,
  },
  listSeparator: {
    height: StyleSheet.hairlineWidth,
    marginLeft: 52,
    backgroundColor: t.color.separator,
  },
  tabBar: {
    alignItems: 'stretch' as const,
    backgroundColor: t.color.canvas,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: t.color.separator,
    flexDirection: 'row' as const,
    flexShrink: 0,
    minHeight: 52,
    paddingHorizontal: t.space.sm,
  },
  tabButton: {
    alignItems: 'center' as const,
    flex: 1,
    justifyContent: 'center' as const,
    minHeight: 52,
  },
});
