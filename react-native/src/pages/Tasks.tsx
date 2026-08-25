import React, {useMemo, useRef, useState} from 'react';
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
  taskGroup,
  type DesktopReadProjection,
  type DomainReadOutcome,
  type TaskGroup,
  type TaskProjection,
} from '../desktopReadClient';
import {FocusPressable} from '../ui/Pressable';
import {ReadStatus} from '../ui/ReadStatus';
import {styles} from '../ui/styles';

const taskGroups: TaskGroup[] = ['Today', 'Tomorrow', 'Later'];

function formatTaskDue(dueAt: number | null): string {
  if (dueAt === null) {
    return 'No due date';
  }
  return new Date(dueAt * 1000).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  });
}

export function TasksPage({
  outcome,
  loading,
}: {
  outcome: DomainReadOutcome<DesktopReadProjection> | null;
  loading: boolean;
}) {
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const nowEpochSeconds = useRef(Math.floor(Date.now() / 1000)).current;
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
    const normalized = query.trim().toLocaleLowerCase();
    return normalized === ''
      ? tasks
      : tasks.filter(task =>
          task.title.toLocaleLowerCase().includes(normalized),
        );
  }, [query, tasks]);
  const grouped = useMemo(
    () =>
      taskGroups.map(label => ({
        label,
        tasks: filtered.filter(
          task => taskGroup(task.dueAt, nowEpochSeconds) === label,
        ),
      })),
    [filtered, nowEpochSeconds],
  );
  const error = outcome?.status === 'error' ? outcome.error : null;
  const filtering = query.trim() !== '';
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
      {loading && outcome === null ? (
        <View style={styles.projectionEmpty}>
          <ActivityIndicator color="#888888" />
          <Text style={styles.projectionEmptyCopy}>Loading tasks…</Text>
        </View>
      ) : error !== null ? (
        <View style={styles.projectionEmpty}>
          <Text style={styles.projectionEmptyTitle}>Tasks unavailable</Text>
          <Text style={styles.projectionEmptyCopy}>
            Saved tasks could not be loaded.
          </Text>
        </View>
      ) : filtered.length === 0 ? (
        <View style={styles.projectionEmpty}>
          <Text style={styles.projectionEmptyTitle}>
            {filtering ? 'No loaded tasks match.' : 'No tasks yet.'}
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
                  return (
                    <FocusPressable
                      accessibilityLabel={`${
                        task.completed ? 'Completed' : 'Open'
                      } task: ${task.title}`}
                      accessibilityRole="button"
                      accessibilityState={{selected}}
                      key={task.id}
                      onPress={() => setSelectedId(task.id)}
                      style={({pressed}) => [
                        styles.taskCard,
                        selected && styles.taskCardSelected,
                        pressed && styles.pressed,
                      ]}>
                      <View
                        accessibilityElementsHidden
                        importantForAccessibility="no-hide-descendants"
                        style={[
                          styles.taskCompletion,
                          task.completed && styles.taskCompletionDone,
                        ]}>
                        {task.completed && (
                          <Text style={styles.taskCheck}>✓</Text>
                        )}
                      </View>
                      <View style={styles.taskCardText}>
                        <Text
                          style={[
                            styles.taskDescription,
                            task.completed && styles.taskDescriptionDone,
                          ]}>
                          {task.title}
                        </Text>
                        <Text style={styles.taskDue}>
                          {task.completed
                            ? `Completed · ${formatTaskDue(task.dueAt)}`
                            : formatTaskDue(task.dueAt)}
                        </Text>
                      </View>
                    </FocusPressable>
                  );
                })}
              </View>
            ),
          )}
          {outcome?.status === 'success' && (
            <ReadStatus label="Tasks" page={outcome.value.page} />
          )}
        </ScrollView>
      )}
      <View
        accessibilityLabel="Task keyboard shortcuts"
        style={styles.taskShortcuts}>
        <Text style={styles.taskShortcut}>Tab · Focus</Text>
        <Text style={styles.taskShortcut}>Enter · Select</Text>
      </View>
    </View>
  );
}
