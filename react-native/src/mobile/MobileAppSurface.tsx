import React, {memo, useCallback, useMemo} from 'react';
import {
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  SafeAreaView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
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

export type MobileRoute = 'home' | 'chat' | 'tasks' | 'apps';

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
  transcript: string;
};

export type MobileAppSurfaceProps = {
  activeRoute: MobileRoute;
  capture: MobileCaptureState;
  device: MobileDeviceState;
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
  onTaskToggle: (id: string, completed: boolean) => void;
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
    empty: `No ${noun} yet`,
    offline: `${noun} will return when you’re online`,
    error: `Couldn’t load ${noun}`,
  }[status];
  return (
    <View
      accessibilityLabel={`${noun} ${status} state`}
      style={styles.statePanel}>
      <Text style={styles.stateText}>{copy}</Text>
    </View>
  );
});

const TaskRow = memo(function TaskRow({
  task,
  onToggle,
}: {
  task: MobileTask;
  onToggle: (id: string, completed: boolean) => void;
}) {
  const handlePress = useCallback(
    () => onToggle(task.id, !task.completed),
    [onToggle, task.completed, task.id],
  );
  return (
    <Pressable
      accessibilityLabel={`${task.completed ? 'Reopen' : 'Complete'} ${
        task.title
      }`}
      accessibilityRole="checkbox"
      accessibilityState={{checked: task.completed}}
      onPress={handlePress}
      style={styles.taskRow}>
      <View style={[styles.checkbox, task.completed && styles.checkboxDone]} />
      <Text style={[styles.taskText, task.completed && styles.taskTextDone]}>
        {task.title}
      </Text>
    </Pressable>
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
  activeRoute,
  askValue,
  capture,
  device,
  mindMapStatus,
  onAskChange,
  onAskSubmit,
  onExpandMindMap,
  onOpenCalls,
  onOpenDevice,
  onOpenSettings,
  onRouteChange,
  onTaskToggle,
  onViewRecaps,
  onViewTasks,
  recaps,
  recapStatus,
  tasks,
  taskStatus,
}: MobileAppSurfaceProps): React.JSX.Element {
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
            <View style={styles.listeningBadge}>
              <Text style={styles.listeningText}>
                {capture.active ? 'Listening' : 'Paused'}
              </Text>
              <View
                style={[
                  styles.captureDot,
                  !capture.active && styles.captureDotPaused,
                ]}
              />
            </View>
            <Text numberOfLines={1} style={styles.transcript}>
              {capture.transcript ||
                (capture.active
                  ? 'Listening for speech…'
                  : 'Capture is paused')}
            </Text>
            <View style={styles.microphoneButton}>
              <Text style={styles.microphoneGlyph}>●</Text>
            </View>
          </View>
        );
      }
      if (item.kind === 'tasks') {
        return (
          <View style={styles.section}>
            <SectionHeader
              action={onViewTasks}
              actionLabel="View All"
              title="Today"
            />
            {taskStatus === 'ready' ? (
              tasks.length === 0 ? (
                <StatePanel noun="tasks" status="empty" />
              ) : (
                <View style={styles.taskCard}>
                  {tasks.slice(0, 3).map(task => (
                    <TaskRow
                      key={task.id}
                      onToggle={onTaskToggle}
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
        ? 'Chat'
        : activeRoute === 'tasks'
        ? 'Tasks'
        : 'Apps';
    return (
      <SafeAreaView style={styles.safeArea}>
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={styles.flex}>
          <View style={styles.secondaryHeader}>
            <Text style={styles.secondaryTitle}>{title}</Text>
            <Pressable
              accessibilityLabel="Open settings"
              accessibilityRole="button"
              onPress={onOpenSettings}
              style={styles.roundButton}>
              <Text style={styles.roundGlyph}>⚙</Text>
            </Pressable>
          </View>
          {activeRoute === 'tasks' ? (
            taskStatus === 'ready' ? (
              <FlatList
                contentContainerStyle={styles.secondaryList}
                data={tasks}
                keyExtractor={task => task.id}
                ListEmptyComponent={<StatePanel noun="tasks" status="empty" />}
                renderItem={({item}) => (
                  <TaskRow onToggle={onTaskToggle} task={item} />
                )}
              />
            ) : (
              <View style={styles.secondaryList}>
                <StatePanel noun="tasks" status={taskStatus} />
              </View>
            )
          ) : activeRoute === 'chat' ? (
            <View style={styles.secondaryEmpty}>
              <Text style={styles.secondaryPrompt}>
                What can I help you find?
              </Text>
              <Text style={styles.secondaryCopy}>
                Ask across your conversations, memories, and tasks.
              </Text>
            </View>
          ) : (
            <View style={styles.secondaryEmpty}>
              <Text style={styles.secondaryPrompt}>Your connected apps</Text>
              <Text style={styles.secondaryCopy}>
                Connected sources and available imports appear here.
              </Text>
            </View>
          )}
          {activeRoute === 'chat' ? (
            <View style={styles.secondaryAskDock}>
              <TextInput
                accessibilityLabel="Ask Omi"
                onChangeText={onAskChange}
                onSubmitEditing={onAskSubmit}
                placeholder="Ask Omi anything…"
                placeholderTextColor={mobileColor.textSubtle}
                returnKeyType="send"
                style={styles.askInput}
                value={askValue}
              />
              <Pressable
                accessibilityLabel="Send to Omi"
                accessibilityRole="button"
                onPress={onAskSubmit}
                style={styles.askButton}>
                <Text style={styles.askGlyph}>●</Text>
              </Pressable>
            </View>
          ) : null}
          <View accessibilityRole="tablist" style={styles.tabBar}>
            {(
              [
                ['home', '⌂', 'Home'],
                ['chat', '◯', 'Chat'],
                ['tasks', '☷', 'Tasks'],
                ['apps', '✚', 'Apps'],
              ] as const
            ).map(([route, glyph, label]) => (
              <Pressable
                accessibilityLabel={label}
                accessibilityRole="tab"
                accessibilityState={{selected: activeRoute === route}}
                key={route}
                onPress={() => onRouteChange(route)}
                style={styles.tabButton}>
                <Text
                  style={[
                    styles.tabGlyph,
                    activeRoute === route && styles.tabGlyphActive,
                  ]}>
                  {glyph}
                </Text>
              </Pressable>
            ))}
          </View>
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
              onPress={onOpenDevice}
              style={styles.deviceButton}>
              <View style={styles.lens} />
              <View
                style={[
                  styles.connectionDot,
                  !device.connected && styles.connectionDotOffline,
                ]}
              />
              <Text style={styles.deviceLabel}>{device.label}</Text>
            </Pressable>
            <Pressable
              accessibilityLabel="Open calls"
              accessibilityRole="button"
              onPress={onOpenCalls}
              style={styles.roundButton}>
              <Text style={styles.roundGlyph}>⌕</Text>
            </Pressable>
          </View>
          <Pressable
            accessibilityLabel="Open settings"
            accessibilityRole="button"
            onPress={onOpenSettings}
            style={styles.roundButton}>
            <Text style={styles.roundGlyph}>⚙</Text>
          </Pressable>
        </View>
        <FlatList
          contentContainerStyle={styles.content}
          data={rows}
          keyExtractor={item => item.key}
          renderItem={renderRow}
          showsVerticalScrollIndicator={false}
        />
        <View style={styles.askDock}>
          <TextInput
            accessibilityLabel="Ask Omi"
            onChangeText={onAskChange}
            onSubmitEditing={onAskSubmit}
            placeholder="Ask Omi anything about your life…"
            placeholderTextColor={mobileColor.textSubtle}
            returnKeyType="send"
            style={styles.askInput}
            value={askValue}
          />
          <Pressable
            accessibilityLabel="Send to Omi"
            accessibilityRole="button"
            onPress={onAskSubmit}
            style={styles.askButton}>
            <Text style={styles.askGlyph}>●</Text>
          </Pressable>
        </View>
        <View accessibilityRole="tablist" style={styles.tabBar}>
          {(
            [
              ['home', '⌂', 'Home'],
              ['chat', '◯', 'Chat'],
              ['tasks', '☷', 'Tasks'],
              ['apps', '✚', 'Apps'],
            ] as const
          ).map(([route, glyph, label]) => (
            <Pressable
              accessibilityLabel={label}
              accessibilityRole="tab"
              accessibilityState={{selected: activeRoute === route}}
              key={route}
              onPress={() => onRouteChange(route)}
              style={styles.tabButton}>
              <Text
                style={[
                  styles.tabGlyph,
                  activeRoute === route && styles.tabGlyphActive,
                ]}>
                {glyph}
              </Text>
            </Pressable>
          ))}
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  flex: {flex: 1},
  safeArea: {backgroundColor: mobileColor.background, flex: 1},
  topBar: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: mobileSpace.md,
    paddingTop: mobileSpace.sm,
  },
  secondaryHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    padding: mobileSpace.md,
  },
  secondaryTitle: {...mobileType.title, color: mobileColor.text},
  secondaryList: {
    flexGrow: 1,
    paddingBottom: 96,
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
  topBarActions: {flexDirection: 'row', gap: mobileSpace.sm},
  deviceButton: {
    alignItems: 'center',
    backgroundColor: mobileColor.surface,
    borderRadius: mobileRadius.round,
    flexDirection: 'row',
    gap: mobileSpace.sm,
    minHeight: 48,
    paddingHorizontal: mobileSpace.md,
  },
  lens: {
    backgroundColor: '#536078',
    borderColor: '#7d89a0',
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
  deviceLabel: {...mobileType.body, color: mobileColor.text, fontWeight: '600'},
  roundButton: {
    alignItems: 'center',
    backgroundColor: mobileColor.surface,
    borderRadius: mobileRadius.round,
    height: 48,
    justifyContent: 'center',
    width: 48,
  },
  roundGlyph: {color: mobileColor.text, fontSize: 22},
  content: {
    gap: mobileSpace.xl,
    paddingBottom: 164,
    paddingHorizontal: mobileSpace.md,
    paddingTop: mobileSpace.xl,
  },
  captureCard: {
    alignItems: 'center',
    backgroundColor: mobileColor.surface,
    borderRadius: mobileRadius.lg,
    flexDirection: 'row',
    gap: mobileSpace.md,
    minHeight: 74,
    padding: mobileSpace.md,
  },
  listeningBadge: {
    alignItems: 'center',
    backgroundColor: mobileColor.surfaceRaised,
    borderRadius: mobileRadius.round,
    flexDirection: 'row',
    gap: mobileSpace.sm,
    paddingHorizontal: mobileSpace.md,
    paddingVertical: mobileSpace.sm,
  },
  listeningText: {...mobileType.body, color: mobileColor.textMuted},
  captureDot: {
    backgroundColor: mobileColor.recording,
    borderRadius: mobileRadius.round,
    height: 8,
    width: 8,
  },
  captureDotPaused: {backgroundColor: mobileColor.textSubtle},
  transcript: {...mobileType.body, color: mobileColor.textMuted, flex: 1},
  microphoneButton: {
    alignItems: 'center',
    backgroundColor: mobileColor.surfaceRaised,
    borderRadius: mobileRadius.round,
    height: 44,
    justifyContent: 'center',
    width: 44,
  },
  microphoneGlyph: {color: mobileColor.text, fontSize: 13},
  section: {gap: mobileSpace.md},
  sectionHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: mobileSpace.sm,
  },
  sectionTitle: {...mobileType.title, color: mobileColor.text},
  quietButton: {
    backgroundColor: mobileColor.surfaceQuiet,
    borderRadius: mobileRadius.round,
    paddingHorizontal: mobileSpace.md,
    paddingVertical: mobileSpace.sm,
  },
  quietButtonText: {...mobileType.caption, color: mobileColor.textMuted},
  taskCard: {
    backgroundColor: mobileColor.surface,
    borderRadius: mobileRadius.lg,
    paddingHorizontal: mobileSpace.md,
    paddingVertical: mobileSpace.sm,
  },
  taskRow: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: mobileSpace.md,
    minHeight: 64,
    paddingVertical: mobileSpace.md,
  },
  checkbox: {
    borderColor: mobileColor.textSubtle,
    borderRadius: mobileRadius.round,
    borderWidth: 2,
    height: 25,
    marginTop: 1,
    width: 25,
  },
  checkboxDone: {backgroundColor: mobileColor.textSubtle},
  taskText: {...mobileType.body, color: mobileColor.text, flex: 1},
  taskTextDone: {
    color: mobileColor.textSubtle,
    textDecorationLine: 'line-through',
  },
  recapCard: {
    backgroundColor: mobileColor.surface,
    borderRadius: mobileRadius.md,
    height: 178,
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
    backgroundColor: '#343f78',
    borderRadius: mobileRadius.round,
    height: 44,
    width: 44,
  },
  mapNode: {
    backgroundColor: '#73446f',
    borderRadius: mobileRadius.round,
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
    bottom: 76,
    flexDirection: 'row',
    left: mobileSpace.md,
    padding: mobileSpace.sm,
    position: 'absolute',
    right: mobileSpace.md,
  },
  askInput: {
    ...mobileType.body,
    color: mobileColor.text,
    flex: 1,
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
  askGlyph: {color: mobileColor.background, fontSize: 14},
  tabBar: {
    alignItems: 'center',
    backgroundColor: 'rgba(10, 10, 12, 0.96)',
    bottom: 0,
    flexDirection: 'row',
    height: 68,
    justifyContent: 'space-around',
    left: 0,
    position: 'absolute',
    right: 0,
  },
  tabButton: {alignItems: 'center', flex: 1, justifyContent: 'center'},
  tabGlyph: {color: mobileColor.textSubtle, fontSize: 30},
  tabGlyphActive: {color: mobileColor.text},
});
