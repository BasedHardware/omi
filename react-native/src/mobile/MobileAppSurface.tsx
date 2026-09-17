import {FocusPressable as Pressable} from '../ui/Pressable';
import React, {memo, useCallback, useMemo, useState} from 'react';
import {
  FlatList,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {
  TaskEditor,
  TaskMutationStatus,
  type TaskMutationProps,
} from '../ui/TaskEditor';
import ArrowUp from 'lucide-react-native/icons/arrow-up';
import House from 'lucide-react-native/icons/house';
import ListFilter from 'lucide-react-native/icons/list-filter';
import MessageCircle from 'lucide-react-native/icons/message-circle';
import Mic from 'lucide-react-native/icons/mic';
import Phone from 'lucide-react-native/icons/phone';
import Puzzle from 'lucide-react-native/icons/puzzle';
import Settings from 'lucide-react-native/icons/settings';
import Check from 'lucide-react-native/icons/check';
import Pencil from 'lucide-react-native/icons/pencil';
import {OmiAvatar} from '../ui/OmiAvatar';
import {useReduceMotion} from '../app/useReduceMotion';
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

export type MobileTask = {
  id: string;
  title: string;
  completed: boolean;
};

export type MobileRecap = {
  id: string;
  title: string;
  dateLabel: string;
};

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
  liveVoiceControl?: React.ReactNode;
  tasks: readonly MobileTask[];
  taskStatus: MobileProjectionStatus;
  recaps: readonly MobileRecap[];
  recapStatus: MobileProjectionStatus;
  mindMapStatus: MobileProjectionStatus;
  askValue: string;
  onAskChange: (value: string) => void;
  onAskSubmit: () => void;
  onOpenSettings: () => void;
  onOpenDevice: () => void;
  onOpenCalls: () => void;
  onRouteChange: (route: MobileRoute) => void;
  onViewTasks: () => void;
  onViewRecaps: () => void;
  onExpandMindMap: () => void;
};

type DashboardRow =
  | {kind: 'capture'; key: 'capture'}
  | {kind: 'tasks'; key: 'tasks'}
  | {kind: 'recaps'; key: 'recaps'}
  | {kind: 'mind-map'; key: 'mind-map'};

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
        <Text style={[styles.taskText, task.completed && styles.taskTextDone]}>
          {task.title}
        </Text>
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

const RecapCard = memo(function RecapCard({recap}: {recap: MobileRecap}) {
  return (
    <View style={styles.recapCard}>
      <Text numberOfLines={3} style={styles.recapTitle}>
        {recap.title}
      </Text>
      <Text style={styles.recapDate}>{recap.dateLabel}</Text>
    </View>
  );
});

const tabItems = [
  {route: 'home' as const, label: 'Home', Icon: House},
  {route: 'chat' as const, label: 'Conversations', Icon: MessageCircle},
  {route: 'tasks' as const, label: 'Tasks', Icon: ListFilter},
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
  return (
    <View accessibilityRole="tablist" style={styles.tabBar}>
      {tabItems.map(({route, label, Icon}) => (
        <Pressable
          accessibilityLabel={label}
          accessibilityRole="tab"
          accessibilityState={{selected: activeRoute === route}}
          key={route}
          onPress={() => onRouteChange(route)}
          style={styles.tabButton}>
          <View
            style={[
              styles.tabIcon,
              activeRoute === route && styles.tabIconActive,
            ]}>
            <Icon
              color={
                activeRoute === route
                  ? mobileColor.text
                  : mobileColor.textSubtle
              }
              size={22}
            />
          </View>
          <Text
            style={[
              styles.tabLabel,
              activeRoute === route && styles.tabLabelActive,
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
  askValue,
  capture,
  device,
  deviceMessage,
  devicePanel,
  settingsContent,
  conversationContent,
  appsContent,
  liveVoiceControl,
  mindMapStatus,
  onAskChange,
  onAskSubmit,
  onExpandMindMap,
  onOpenCalls,
  onOpenDevice,
  onOpenSettings,
  onRouteChange,
  onTaskToggle,
  onTaskEdit,
  busyTaskId = null,
  taskMutationError = null,
  onRetryTaskMutation,
  onDismissTaskMutation,
  writesAvailable = false,
  onViewRecaps,
  onViewTasks,
  recaps,
  recapStatus,
  tasks,
  taskStatus,
}: MobileAppSurfaceProps): React.JSX.Element {
  const reduceMotion = useReduceMotion();
  const [greeting, setGreeting] = useState(0);
  const canAsk = askValue.trim().length > 0;
  const submitAsk = () => {
    if (canAsk) {
      onAskSubmit();
    }
  };
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const selectedTask = tasks.find(task => task.id === selectedTaskId);
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
      {kind: 'capture', key: 'capture'},
      {kind: 'tasks', key: 'tasks'},
      {kind: 'recaps', key: 'recaps'},
      {kind: 'mind-map', key: 'mind-map'},
    ],
    [],
  );

  const renderRow = useCallback(
    ({item}: {item: DashboardRow}) => {
      if (item.kind === 'capture') {
        return (
          <View style={styles.captureCard}>
            <View style={styles.captureHeader}>
              <View style={styles.listeningBadge}>
                <Text style={styles.listeningText}>
                  {capture.active
                    ? capture.waitingForAudio
                      ? 'Waiting for audio'
                      : 'Listening'
                    : 'Paused'}
                </Text>
                <View
                  style={[
                    styles.captureDot,
                    (!capture.active || capture.waitingForAudio) &&
                      styles.captureDotPaused,
                  ]}
                />
              </View>
              <View style={styles.microphoneButton}>
                <Mic color={mobileColor.text} size={18} />
              </View>
            </View>
            <Text numberOfLines={2} style={styles.transcript}>
              {capture.transcript ||
                (capture.active
                  ? capture.waitingForAudio
                    ? 'Your Omi is connected. Waiting for audio…'
                    : 'Listening for speech…'
                  : 'Capture is paused')}
            </Text>
          </View>
        );
      }
      if (item.kind === 'tasks') {
        return (
          <View style={styles.section}>
            <SectionHeader
              action={onViewTasks}
              actionLabel="View All"
              title="Tasks"
            />
            {taskFeedback}
            {taskStatus === 'ready' ? (
              tasks.length === 0 ? (
                <StatePanel noun="tasks" status="empty" />
              ) : (
                <View style={styles.taskCard}>
                  {tasks.slice(0, 3).map(task => (
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
      if (item.kind === 'recaps') {
        return (
          <View style={styles.section}>
            <SectionHeader
              action={onViewRecaps}
              actionLabel="View All"
              title="Daily Recaps"
            />
            {recapStatus === 'ready' ? (
              recaps.length === 0 ? (
                <StatePanel noun="recaps" status="empty" />
              ) : (
                <FlatList
                  data={recaps}
                  horizontal
                  keyExtractor={recap => recap.id}
                  renderItem={({item: recap}) => <RecapCard recap={recap} />}
                  showsHorizontalScrollIndicator={false}
                />
              )
            ) : (
              <StatePanel noun="recaps" status={recapStatus} />
            )}
          </View>
        );
      }
      return (
        <View style={styles.section}>
          <SectionHeader
            action={onExpandMindMap}
            actionLabel="Expand"
            title="Mind Map"
          />
          {mindMapStatus === 'ready' ? (
            <View accessibilityLabel="Mind map preview" style={styles.mapCard}>
              <View style={styles.mapNodeLarge} />
              <View style={[styles.mapNode, styles.mapNodeLeft]} />
              <View style={[styles.mapNode, styles.mapNodeRight]} />
              <View style={[styles.mapNode, styles.mapNodeBottom]} />
            </View>
          ) : (
            <StatePanel noun="mind map" status={mindMapStatus} />
          )}
        </View>
      );
    },
    [
      capture,
      mindMapStatus,
      onExpandMindMap,
      onTaskToggle,
      onTaskEdit,
      writesAvailable,
      busyTaskId,
      taskFeedback,
      onViewRecaps,
      onViewTasks,
      recaps,
      recapStatus,
      tasks,
      taskStatus,
    ],
  );

  if (activeRoute !== 'home') {
    const title =
      activeRoute === 'chat'
        ? 'Conversations'
        : activeRoute === 'tasks'
        ? 'Tasks'
        : activeRoute === 'settings'
        ? 'Settings'
        : 'Apps';
    return (
      <SafeAreaView style={styles.safeArea}>
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={styles.flex}>
          <View style={styles.secondaryHeader}>
            <View style={styles.pageHeading}>
              <Text accessibilityRole="header" style={styles.secondaryTitle}>
                {title}
              </Text>
              <Text style={styles.pageSubtitle}>
                {activeRoute === 'chat'
                  ? 'A place for what you want to remember.'
                  : activeRoute === 'tasks'
                  ? 'A little follow-through.'
                  : activeRoute === 'apps'
                  ? 'Make Omi your own.'
                  : 'Your Omi, your way.'}
              </Text>
            </View>
            {activeRoute !== 'settings' && (
              <Pressable
                accessibilityLabel="Open settings"
                accessibilityRole="button"
                onPress={onOpenSettings}
                style={styles.roundButton}>
                <Settings color={mobileColor.text} size={20} />
              </Pressable>
            )}
          </View>
          <View style={styles.flex}>
            {activeRoute === 'settings' ? (
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
          <View style={styles.topBarActions}>
            <Pressable
              accessibilityLabel="Open Omi device"
              accessibilityRole="button"
              accessibilityState={{expanded: devicePanel != null}}
              onPress={onOpenDevice}
              style={styles.deviceButton}>
              <View style={styles.lens} />
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
            <Pressable
              accessibilityLabel="Open calls"
              accessibilityRole="button"
              onPress={onOpenCalls}
              style={styles.roundButton}>
              <Phone color={mobileColor.text} size={20} />
            </Pressable>
          </View>
          <Pressable
            accessibilityLabel="Open settings"
            accessibilityRole="button"
            onPress={onOpenSettings}
            style={styles.roundButton}>
            <Settings color={mobileColor.text} size={20} />
          </Pressable>
        </View>
        {liveVoiceControl && (
          <View style={styles.liveVoiceRow}>{liveVoiceControl}</View>
        )}
        {deviceMessage && (
          <Text accessibilityRole="alert" style={styles.deviceMessage}>
            {deviceMessage}
          </Text>
        )}
        <FlatList
          contentContainerStyle={styles.content}
          data={rows}
          ListHeaderComponent={
            <View>
              <View style={styles.homeHeading}>
                <View style={styles.pageHeading}>
                  <Text style={styles.homeEyebrow}>YOUR PERSONAL CONTEXT</Text>
                  <Text accessibilityRole="header" style={styles.homeTitle}>
                    A little space for your day.
                  </Text>
                </View>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="Say hello to Omi"
                  onPress={() => setGreeting(value => value + 1)}
                  style={styles.greeting}>
                  <OmiAvatar
                    tone="ink"
                    size={60}
                    motion="arrive"
                    motionKey={String(greeting)}
                    reduceMotion={reduceMotion}
                  />
                </Pressable>
              </View>
              {devicePanel ? <View>{devicePanel}</View> : null}
            </View>
          }
          keyExtractor={item => item.key}
          renderItem={renderRow}
          showsVerticalScrollIndicator={false}
        />
        <View style={styles.askDock}>
          <TextInput
            accessibilityLabel="Ask Omi"
            onChangeText={onAskChange}
            onSubmitEditing={submitAsk}
            placeholder="Ask about your day…"
            placeholderTextColor={mobileColor.textSubtle}
            returnKeyType="send"
            style={styles.askInput}
            value={askValue}
          />
          <Pressable
            accessibilityLabel="Send to Omi"
            accessibilityRole="button"
            accessibilityState={{disabled: !canAsk}}
            disabled={!canAsk}
            onPress={submitAsk}
            style={[styles.askButton, !canAsk && styles.askButtonDisabled]}>
            <ArrowUp color={mobileColor.background} size={18} />
          </Pressable>
        </View>
        <MobileTabBar activeRoute={activeRoute} onRouteChange={onRouteChange} />
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  flex: {flex: 1},
  liveVoiceRow: {paddingHorizontal: 16, paddingTop: 8},
  safeArea: {backgroundColor: mobileColor.background, flex: 1},
  homeHeading: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
    paddingBottom: 4,
  },
  pageHeading: {flex: 1, gap: 8},
  pageSubtitle: {fontSize: 14, lineHeight: 20, color: mobileColor.textMuted},
  greeting: {
    height: 64,
    width: 64,
    alignItems: 'center',
    justifyContent: 'center',
  },
  homeEyebrow: {
    fontSize: 10,
    letterSpacing: 1.5,
    color: mobileColor.textSubtle,
    fontWeight: '600',
  },
  homeTitle: {
    fontSize: 28,
    lineHeight: 34,
    letterSpacing: -0.8,
    color: mobileColor.text,
    maxWidth: 280,
  },
  topBar: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: mobileSpace.sm,
    paddingHorizontal: mobileSpace.md,
    paddingTop: mobileSpace.sm,
  },
  secondaryHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    padding: mobileSpace.md,
    gap: 16,
  },
  secondaryTitle: {
    fontSize: 28,
    lineHeight: 34,
    fontWeight: '600',
    letterSpacing: -0.7,
    color: mobileColor.text,
  },
  secondaryList: {
    flexGrow: 1,
    paddingBottom: 24,
    paddingHorizontal: mobileSpace.md,
    paddingTop: mobileSpace.lg,
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
  secondaryAskDock: {
    alignItems: 'center',
    backgroundColor: mobileColor.surface,
    borderColor: mobileColor.border,
    borderRadius: mobileRadius.round,
    borderWidth: StyleSheet.hairlineWidth,
    bottom: 76,
    flexDirection: 'row',
    left: mobileSpace.md,
    padding: mobileSpace.sm,
    position: 'absolute',
    right: mobileSpace.md,
  },
  topBarActions: {flexDirection: 'row', flexShrink: 1, gap: mobileSpace.sm},
  deviceButton: {
    flexShrink: 1,
    alignItems: 'center',
    backgroundColor: mobileColor.surface,
    borderRadius: mobileRadius.round,
    flexDirection: 'row',
    gap: mobileSpace.sm,
    minHeight: 48,
    paddingHorizontal: mobileSpace.md,
  },
  lens: {
    backgroundColor: '#292b27',
    borderColor: '#696e63',
    borderRadius: mobileRadius.round,
    borderWidth: 2,
    height: 25,
    width: 25,
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
  roundButton: {
    flexShrink: 0,
    alignItems: 'center',
    backgroundColor: mobileColor.surface,
    borderRadius: mobileRadius.round,
    height: 48,
    justifyContent: 'center',
    width: 48,
  },
  roundGlyph: {color: mobileColor.text, fontSize: 22},
  content: {
    gap: mobileSpace.lg,
    paddingBottom: 24,
    paddingHorizontal: mobileSpace.md,
    paddingTop: mobileSpace.xl,
  },
  captureCard: {
    alignItems: 'stretch',
    backgroundColor: mobileColor.surface,
    borderWidth: 1,
    borderColor: mobileColor.border,
    borderRadius: mobileRadius.lg,
    gap: mobileSpace.sm,
    minHeight: 74,
    padding: mobileSpace.md,
  },
  captureHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  listeningBadge: {
    alignItems: 'center',
    borderRadius: mobileRadius.round,
    flexDirection: 'row',
    gap: mobileSpace.sm,
  },
  listeningText: {...mobileType.caption, color: mobileColor.textMuted},
  captureDot: {
    backgroundColor: mobileColor.recording,
    borderRadius: mobileRadius.round,
    height: 8,
    width: 8,
  },
  captureDotPaused: {backgroundColor: mobileColor.textSubtle},
  transcript: {...mobileType.body, color: mobileColor.textMuted},
  microphoneButton: {
    alignItems: 'center',
    backgroundColor: mobileColor.surfaceRaised,
    borderRadius: mobileRadius.round,
    height: 44,
    justifyContent: 'center',
    width: 44,
  },
  microphoneGlyph: {color: mobileColor.text, fontSize: 13},
  section: {gap: mobileSpace.sm},
  sectionHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 2,
  },
  sectionTitle: {
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
  taskCard: {
    backgroundColor: mobileColor.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: mobileColor.border,
    borderRadius: mobileRadius.lg,
    paddingHorizontal: mobileSpace.md,
    paddingVertical: mobileSpace.sm,
  },
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
  taskText: {fontSize: 15, lineHeight: 22, color: mobileColor.text, flex: 1},
  taskTextDone: {
    color: mobileColor.textSubtle,
    textDecorationLine: 'line-through',
  },
  recapCard: {
    backgroundColor: mobileColor.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: mobileColor.border,
    borderRadius: mobileRadius.md,
    minHeight: 136,
    gap: 20,
    justifyContent: 'space-between',
    marginRight: mobileSpace.sm,
    padding: mobileSpace.md,
    width: 250,
  },
  recapTitle: {...mobileType.body, color: mobileColor.text},
  recapDate: {
    ...mobileType.caption,
    alignSelf: 'flex-end',
    backgroundColor: mobileColor.surfaceQuiet,
    borderRadius: mobileRadius.round,
    color: mobileColor.textMuted,
    paddingHorizontal: mobileSpace.md,
    paddingVertical: mobileSpace.xs,
  },
  mapCard: {
    alignItems: 'center',
    backgroundColor: mobileColor.surfaceQuiet,
    borderColor: mobileColor.border,
    borderRadius: mobileRadius.md,
    borderWidth: StyleSheet.hairlineWidth,
    height: 150,
    justifyContent: 'center',
    overflow: 'hidden',
  },
  mapNodeLarge: {
    backgroundColor: mobileColor.surfaceRaised,
    borderColor: mobileColor.border,
    borderRadius: 22,
    borderWidth: StyleSheet.hairlineWidth,
    height: 44,
    width: 44,
  },
  mapNode: {
    backgroundColor: mobileColor.surface,
    borderColor: mobileColor.border,
    borderRadius: 11,
    borderWidth: StyleSheet.hairlineWidth,
    height: 22,
    position: 'absolute',
    width: 22,
  },
  mapNodeLeft: {left: '24%', top: '32%'},
  mapNodeRight: {right: '22%', top: '26%'},
  mapNodeBottom: {bottom: '18%', right: '35%'},
  statePanel: {
    alignItems: 'center',
    backgroundColor: mobileColor.surface,
    borderRadius: mobileRadius.md,
    minHeight: 96,
    justifyContent: 'center',
    padding: mobileSpace.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: mobileColor.border,
  },
  stateText: {
    ...mobileType.body,
    color: mobileColor.textMuted,
    textAlign: 'center',
  },
  askDock: {
    alignItems: 'center',
    backgroundColor: mobileColor.surface,
    borderColor: mobileColor.border,
    borderRadius: mobileRadius.round,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    marginHorizontal: mobileSpace.md,
    marginTop: 8,
    marginBottom: 8,
    padding: 6,
  },
  askInput: {
    ...mobileType.body,
    color: mobileColor.text,
    flex: 1,
    minWidth: 0,
    minHeight: 44,
    paddingHorizontal: mobileSpace.md,
  },
  askButton: {
    alignItems: 'center',
    backgroundColor: mobileColor.accent,
    borderRadius: mobileRadius.round,
    height: 46,
    justifyContent: 'center',
    width: 46,
  },
  askButtonDisabled: {opacity: 0.35},
  askGlyph: {color: mobileColor.background, fontSize: 14},
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
  },
  tabButton: {
    alignItems: 'center',
    flex: 1,
    justifyContent: 'center',
    minHeight: 60,
    gap: 3,
  },
  tabIcon: {paddingVertical: 4, paddingHorizontal: 12, borderRadius: 12},
  tabIconActive: {backgroundColor: mobileColor.surfaceRaised},
  tabLabel: {fontSize: 9, color: mobileColor.textSubtle},
  tabLabelActive: {color: mobileColor.text},
  tabGlyph: {color: mobileColor.textSubtle, fontSize: 30},
  tabGlyphActive: {color: mobileColor.text},
});
