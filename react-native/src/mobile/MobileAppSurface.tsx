import {FocusPressable as Pressable} from '../ui/Pressable';
import React, {useCallback, useMemo, useRef, useState} from 'react';
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
import Mic from 'lucide-react-native/icons/mic';
import Settings from 'lucide-react-native/icons/settings';
import {OmiAvatar} from '../ui/OmiAvatar';
import {conversationGroupLabel} from '../desktopReadClient';
import {
  TimelineEventRow,
  TimelineStatePanel,
  TimelineTaskRow,
  buildTimelineItems,
  type TimelineProjectionStatus,
  type TimelineTask,
} from '../timeline/TimelineHome';
import type {
  MixedTimelineItem,
  TimelineConversation,
  TimelineRecall,
} from '../timeline/mixedTimeline';
import {
  mobileColor,
  mobileRadius,
  mobileSpace,
  mobileType,
} from './mobileTokens';

export type MobileProjectionStatus = TimelineProjectionStatus;
export type MobileRoute = 'home' | 'chat' | 'tasks' | 'apps' | 'settings';
export type MobileTask = TimelineTask;

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
  conversations?: readonly TimelineConversation[];
  recall?: readonly TimelineRecall[];
  timelineStatus?: MobileProjectionStatus;
  timelineNotice?: string | null;
  onOpenTimelineItem?: (item: MixedTimelineItem) => void;
  omnibar: React.ReactNode;
  chatContent?: React.ReactNode;
  searchQuery?: string;
  onOpenDevice: () => void;
  onOpenSettings?: () => void;
  onOpenCalls?: () => void;
  onRouteChange: (route: MobileRoute) => void;
  onViewTasks?: () => void;
};

type HomeRow =
  | {kind: 'tasks'; key: 'tasks'}
  | {kind: 'day'; key: string; label: string; items: MixedTimelineItem[]};

export function MobileAppSurface({
  taskPagination,
  activeRoute,
  omnibar,
  chatContent,
  searchQuery = '',
  capture,
  device,
  deviceMessage,
  devicePanel,
  settingsContent,
  conversationContent,
  appsContent,

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
  conversations = [],
  recall = [],
  timelineStatus = 'ready',
  timelineNotice = null,
  onOpenTimelineItem,
  tasks,
  taskStatus,
}: MobileAppSurfaceProps): React.JSX.Element {
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const nowEpochMilliseconds = useRef(Date.now()).current;
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

  const timelineItems = useMemo(
    () =>
      buildTimelineItems({
        conversations,
        recall,
        query: searchQuery,
      }),
    [conversations, recall, searchQuery],
  );

  const rows = useMemo<HomeRow[]>(() => {
    const next: HomeRow[] = [];
    if (timelineStatus !== 'ready' || timelineItems.length === 0) {
      next.push({kind: 'day', key: 'timeline-state', label: '', items: []});
      next.push({kind: 'tasks', key: 'tasks'});
      return next;
    }
    const groups = new Map<string, MixedTimelineItem[]>();
    for (const item of timelineItems) {
      const label =
        item.atMs === null || !Number.isFinite(item.atMs)
          ? 'Date unavailable'
          : conversationGroupLabel(
              new Date(item.atMs).toISOString(),
              nowEpochMilliseconds,
            );
      const bucket = groups.get(label);
      if (bucket) {
        bucket.push(item);
      } else {
        groups.set(label, [item]);
      }
    }
    for (const [label, items] of groups) {
      next.push({kind: 'day', key: `day:${label}`, label, items});
    }
    if (![...groups.keys()].includes('Today')) {
      next.unshift({kind: 'tasks', key: 'tasks'});
    }
    return next;
  }, [
    timelineItems,
    timelineStatus,
    nowEpochMilliseconds,
  ]);

  const renderRow = useCallback(
    ({item}: {item: HomeRow}) => {
      if (item.kind === 'tasks') {
        const openTasks = tasks.filter(task => !task.completed);
        return (
          <View style={styles.section}>
            {taskFeedback}
            {taskStatus === 'ready' ? (
              openTasks.length === 0 ? (
                <TimelineStatePanel noun="action items" status="empty" />
              ) : (
                openTasks.slice(0, 5).map((task, index) => (
                  <TimelineTaskRow
                    key={task.id}
                    onToggle={writesAvailable ? onTaskToggle : undefined}
                    onEdit={
                      writesAvailable && onTaskEdit
                        ? setSelectedTaskId
                        : undefined
                    }
                    busy={busyTaskId !== null}
                    last={index === openTasks.slice(0, 5).length - 1}
                    task={task}
                  />
                ))
              )
            ) : (
              <TimelineStatePanel noun="action items" status={taskStatus} />
            )}
          </View>
        );
      }
      if (timelineStatus !== 'ready') {
        return <TimelineStatePanel noun="timeline" status={timelineStatus} />;
      }
      if (item.items.length === 0) {
        return <TimelineStatePanel noun="timeline" status="empty" />;
      }
      return (
        <View style={styles.section}>
          <Text style={styles.dayLabel}>{item.label}</Text>
          {item.label === 'Today' ? (
            <>
              {taskFeedback}
              {taskStatus === 'ready'
                ? tasks
                    .filter(task => !task.completed)
                    .slice(0, 5)
                    .map(task => (
                      <TimelineTaskRow
                        key={task.id}
                        onToggle={writesAvailable ? onTaskToggle : undefined}
                        onEdit={
                          writesAvailable && onTaskEdit
                            ? setSelectedTaskId
                            : undefined
                        }
                        busy={busyTaskId !== null}
                        last={false}
                        task={task}
                      />
                    ))
                : (
                    <TimelineStatePanel
                      noun="action items"
                      status={taskStatus}
                    />
                  )}
            </>
          ) : null}
          {item.items.map((event, index) => (
            <TimelineEventRow
              key={`${event.kind}:${event.id}`}
              item={event}
              last={index === item.items.length - 1}
              onPress={onOpenTimelineItem}
            />
          ))}
        </View>
      );
    },
    [
      tasks,
      taskStatus,
      taskFeedback,
      writesAvailable,
      onTaskToggle,
      onTaskEdit,
      busyTaskId,
      timelineStatus,
      onOpenTimelineItem,
    ],
  );

  const overlay =
    chatContent ||
    activeRoute === 'settings' ||
    (activeRoute === 'apps' && appsContent) ||
    activeRoute === 'tasks' ||
    activeRoute === 'chat';

  const stage = chatContent ? (
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
          <TimelineStatePanel noun="action items" status="empty" />
        }
        renderItem={({item}) => (
          <TimelineTaskRow
            onToggle={writesAvailable ? onTaskToggle : undefined}
            onEdit={
              writesAvailable && onTaskEdit ? setSelectedTaskId : undefined
            }
            busy={busyTaskId !== null}
            task={item}
          />
        )}
      />
    ) : (
      <View style={[styles.secondaryList, styles.flex]}>
        <TimelineStatePanel noun="action items" status={taskStatus} />
        {taskPagination}
      </View>
    )
  ) : activeRoute === 'chat' ? (
    conversationContent ?? (
      <TimelineStatePanel noun="conversations" status="error" />
    )
  ) : null;

  return (
    <SafeAreaView style={styles.safeArea}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.flex}>
        <View style={styles.topBar}>
          <View accessibilityLabel="Omi">
            <OmiAvatar tone="ink" size={36} reduceMotion />
          </View>
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
            <View
              accessibilityLabel={
                capture.active
                  ? capture.waitingForAudio
                    ? 'Capture waiting for audio'
                    : 'Capture listening'
                  : 'Capture paused'
              }
              style={styles.captureChip}>
              <Mic
                color={
                  capture.active && !capture.waitingForAudio
                    ? mobileColor.text
                    : mobileColor.textMuted
                }
                size={16}
              />
              <View
                style={[
                  styles.captureDot,
                  (!capture.active || capture.waitingForAudio) &&
                    styles.captureDotPaused,
                ]}
              />
            </View>
            <Pressable
              accessibilityLabel="Settings"
              accessibilityRole="button"
              accessibilityState={{selected: activeRoute === 'settings'}}
              onPress={() =>
                onOpenSettings
                  ? onOpenSettings()
                  : onRouteChange('settings')
              }
              style={styles.roundButton}>
              <Settings color={mobileColor.text} size={20} />
            </Pressable>
          </View>
        </View>
        {deviceMessage && (
          <Text accessibilityRole="alert" style={styles.deviceMessage}>
            {deviceMessage}
          </Text>
        )}
        {overlay ? (
          <View style={[styles.flex, styles.stage]}>{stage}</View>
        ) : (
          <FlatList
            contentContainerStyle={styles.content}
            data={rows}
            ListHeaderComponent={
              <View>{devicePanel ? <View>{devicePanel}</View> : null}</View>
            }
            keyExtractor={item => item.key}
            renderItem={renderRow}
            showsVerticalScrollIndicator={false}
          />
        )}
        {omnibar}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  flex: {flex: 1},
  stage: {paddingTop: 4},
  safeArea: {backgroundColor: mobileColor.background, flex: 1},
  topBar: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: mobileSpace.sm,
    paddingHorizontal: mobileSpace.md,
    paddingTop: 4,
    paddingBottom: 4,
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
  content: {
    gap: 16,
    paddingBottom: 140,
    paddingHorizontal: mobileSpace.md,
    paddingTop: 8,
  },
  captureChip: {
    alignItems: 'center',
    backgroundColor: mobileColor.surface,
    borderRadius: mobileRadius.round,
    flexDirection: 'row',
    flexShrink: 0,
    gap: 6,
    height: 48,
    justifyContent: 'center',
    paddingHorizontal: 12,
  },
  captureDot: {
    backgroundColor: mobileColor.recording,
    borderRadius: mobileRadius.round,
    height: 8,
    width: 8,
  },
  captureDotPaused: {backgroundColor: mobileColor.textSubtle},
  section: {gap: 2},
  dayLabel: {
    ...mobileType.caption,
    color: mobileColor.textMuted,
    marginBottom: 6,
  },
  secondaryList: {
    flexGrow: 1,
    paddingBottom: 24,
    paddingHorizontal: mobileSpace.md,
    paddingTop: mobileSpace.lg,
  },
});
