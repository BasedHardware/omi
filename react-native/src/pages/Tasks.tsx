import React, {useEffect, useMemo, useRef, useState} from 'react';
import {
  ActivityIndicator,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import Search from 'lucide-react-native/icons/search';
import {
  desktopBackendUnavailableCopy,
  formatTaskDue,
  taskDisplayTitle,
  taskGroup,
  taskIndentPadding,
  visibleDisplayText,
  type DesktopReadProjection,
  type DomainReadOutcome,
  type TaskGroup,
  type TaskProjection,
} from '../desktopReadClient';
import {FocusPressable} from '../ui/Pressable';
import {
  TaskEditor,
  TaskMutationStatus,
  type TaskMutationProps,
} from '../ui/TaskEditor';
import {ReadStatus, emptyLibraryCopy} from '../ui/ReadStatus';
import {styles} from '../ui/styles';
import {goalProgressCopy, loadOmiGoals, type OmiGoal} from '../legacyOmiGoals';
import type {OmiBackend} from '../omiNativeTypes';

const taskGroups: TaskGroup[] = [
  'Today',
  'Tomorrow',
  'Later',
  'No Deadline',
  'Overdue',
];

export function TasksPage({
  outcome,
  loading,
  taskPagination,
  onTaskToggle,
  onTaskEdit,
  busyTaskId = null,
  taskMutationError = null,
  onRetryTaskMutation,
  onDismissTaskMutation,
  writesAvailable,
  taskNotice = null,
  onRefresh,
  backend = null,
}: TaskMutationProps & {
  outcome: DomainReadOutcome<DesktopReadProjection> | null;
  loading: boolean;
  taskPagination?: React.ReactNode;
  taskNotice?: string | null;
  onRefresh?: () => void;
  backend?: OmiBackend | null;
}) {
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [goals, setGoals] = useState<OmiGoal[]>([]);
  const nowMs = useRef(Date.now()).current;
  const tasks = useMemo(
    () =>
      outcome?.status === 'success'
        ? outcome.value.items.filter(
            (item): item is TaskProjection => item.kind === 'task',
          )
        : [],
    [outcome],
  );
  const filtered = useMemo(() => {
    const normalized = visibleDisplayText(query).toLocaleLowerCase();
    return normalized === ''
      ? tasks
      : tasks.filter(task =>
          `${task.title}\n${taskDisplayTitle(task)}`
            .toLocaleLowerCase()
            .includes(normalized),
        );
  }, [query, tasks]);
  const grouped = useMemo(
    () =>
      taskGroups.map(label => ({
        label,
        tasks: filtered.filter(
          task => taskGroup(task.dueAt, nowMs, task.createdAt) === label,
        ),
      })),
    [filtered, nowMs],
  );
  const error = outcome?.status === 'error' ? outcome.error : null;
  const filtering = visibleDisplayText(query) !== '';
  useEffect(() => {
    if (backend === undefined || backend === null) {
      setGoals([]);
      return;
    }
    let cancelled = false;
    loadOmiGoals(backend)
      .then(rows => {
        if (!cancelled) {
          setGoals(rows);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setGoals([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [backend, loading]);
  return (
    <View style={styles.tasksPage}>
      <Text
        style={[
          styles.projectionTitle,
          Platform.OS === 'macos' && styles.macPrimaryText,
        ]}>
        Tasks
      </Text>
      <View style={styles.taskSearchBox}>
        <Search accessible={false} color="#777777" size={17} />
        <TextInput
          accessibilityLabel="Search loaded tasks"
          onChangeText={setQuery}
          placeholder="Search loaded tasks"
          placeholderTextColor="#666666"
          style={styles.memorySearchInput}
          value={query}
        />
      </View>
      <TaskMutationStatus
        writesAvailable={writesAvailable}
        taskMutationError={taskMutationError}
        onRetryTaskMutation={onRetryTaskMutation}
        onDismissTaskMutation={onDismissTaskMutation}
        busyTaskId={busyTaskId}
      />
      {goals.length > 0 ? (
        <View>
          <Text style={styles.projectionEmptyTitle}>Goals</Text>
          {goals.map(goal => (
            <View key={goal.id}>
              <Text numberOfLines={1} style={styles.resultTitle}>
                {goal.title}
              </Text>
              <Text style={styles.conversationRowTime}>
                {goalProgressCopy(goal.current, goal.target)}
              </Text>
            </View>
          ))}
        </View>
      ) : null}
      {onRefresh && error !== desktopBackendUnavailableCopy && (
        <FocusPressable
          accessibilityRole="button"
          accessibilityLabel="Refresh tasks"
          disabled={loading}
          onPress={onRefresh}
          style={{minHeight: 44, justifyContent: 'center'}}>
          <Text style={styles.projectionEmptyCopy}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </Text>
        </FocusPressable>
      )}
      {loading && outcome === null ? (
        <View style={styles.projectionEmpty}>
          <ActivityIndicator color="#888888" />
          <Text style={styles.projectionEmptyCopy}>Loading tasks…</Text>
        </View>
      ) : error !== null ? (
        <View style={styles.projectionEmpty}>
          <Text style={styles.projectionEmptyTitle}>Tasks unavailable</Text>
          <Text style={styles.projectionEmptyCopy}>{error}</Text>
        </View>
      ) : filtered.length === 0 ? (
        <View style={styles.projectionEmpty}>
          <Text style={styles.projectionEmptyTitle}>
            {emptyLibraryCopy(
              'Tasks',
              outcome?.status === 'success' ? outcome.value.page : null,
              filtering,
              'No loaded tasks match.',
              'No tasks yet.',
              taskNotice === desktopBackendUnavailableCopy,
            )}
          </Text>
          {filtering && (
            <Text style={styles.projectionEmptyCopy}>
              Search covers task descriptions already loaded on this device.
            </Text>
          )}
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.taskList}>
          {grouped.map(group =>
            group.tasks.length === 0 ? null : (
              <View key={group.label} style={styles.taskGroup}>
                <View style={styles.taskGroupHeader}>
                  <Text style={styles.taskGroupTitle}>{group.label}</Text>
                  <Text style={styles.taskGroupCount}>
                    {group.tasks.length}
                  </Text>
                </View>
                {group.tasks.map(task => {
                  const selected = task.id === selectedId;
                  const indentPad = taskIndentPadding(task.indentLevel);
                  return (
                    <View key={task.id}>
                      <View
                        style={[
                          styles.taskCard,
                          selected && styles.taskCardSelected,
                          indentPad > 0 ? {paddingLeft: 14 + indentPad} : null,
                        ]}>
                        {indentPad > 0 ? (
                          <View
                            accessibilityLabel="Nested task"
                            style={taskStyles.indentLead}
                          />
                        ) : null}
                        <FocusPressable
                          accessibilityLabel={`${
                            writesAvailable
                              ? task.completed
                                ? 'Reopen'
                                : 'Complete'
                              : task.completed
                              ? 'Completed'
                              : 'Task'
                          } ${taskDisplayTitle(task)}`}
                          accessibilityRole={
                            writesAvailable && onTaskToggle
                              ? 'checkbox'
                              : 'text'
                          }
                          accessibilityState={{
                            checked: task.completed,
                            disabled:
                              !writesAvailable ||
                              !onTaskToggle ||
                              busyTaskId !== null,
                            busy: busyTaskId === task.id,
                          }}
                          disabled={
                            !writesAvailable ||
                            !onTaskToggle ||
                            busyTaskId !== null
                          }
                          onPress={() => onTaskToggle?.(task.id)}
                          style={taskStyles.toggle}>
                          <View
                            style={[
                              styles.taskCompletion,
                              task.completed && styles.taskCompletionDone,
                            ]}>
                            {task.completed && (
                              <Text style={styles.taskCheck}>✓</Text>
                            )}
                          </View>
                        </FocusPressable>
                        <FocusPressable
                          accessibilityLabel={
                            task.completed
                              ? `Completed task: ${taskDisplayTitle(task)}`
                              : writesAvailable && onTaskEdit
                              ? `Open task: ${taskDisplayTitle(task)}`
                              : `Task: ${taskDisplayTitle(task)}`
                          }
                          accessibilityRole="button"
                          accessibilityState={{selected}}
                          onPress={() => setSelectedId(task.id)}
                          style={styles.taskCardText}>
                          <Text
                            style={[
                              styles.taskDescription,
                              task.completed && styles.taskDescriptionDone,
                            ]}>
                            {taskDisplayTitle(task)}
                          </Text>
                          <Text style={styles.taskDue}>
                            {task.completed
                              ? `Completed · ${formatTaskDue(task.dueAt)}`
                              : formatTaskDue(task.dueAt)}
                          </Text>
                          {task.exportCopy !== undefined ? (
                            <Text style={styles.taskDue}>
                              {task.exportCopy}
                            </Text>
                          ) : null}
                        </FocusPressable>
                      </View>
                      {selected && writesAvailable && onTaskEdit && (
                        <TaskEditor
                          id={task.id}
                          title={task.title.trim()}
                          busy={busyTaskId !== null}
                          failed={taskMutationError !== null}
                          onSave={onTaskEdit}
                          onClose={() => setSelectedId(null)}
                        />
                      )}
                    </View>
                  );
                })}
              </View>
            ),
          )}
          {outcome?.status === 'success' && (
            <ReadStatus
              continueUnavailable={taskNotice === desktopBackendUnavailableCopy}
              label="Tasks"
              page={outcome.value.page}
            />
          )}
        </ScrollView>
      )}
      {taskPagination}
      <View
        accessibilityLabel="Task keyboard shortcuts"
        style={styles.taskShortcuts}>
        <Text style={styles.taskShortcut}>Tab · Focus</Text>
        <Text style={styles.taskShortcut}>Enter · Select</Text>
      </View>
    </View>
  );
}

const taskStyles = StyleSheet.create({
  toggle: {
    minHeight: 44,
    minWidth: 44,
    justifyContent: 'center',
    alignItems: 'center',
  },
  indentLead: {
    backgroundColor: '#555555',
    borderRadius: 1,
    height: 20,
    marginRight: 8,
    width: 1.5,
  },
});
