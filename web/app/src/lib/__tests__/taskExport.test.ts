import { describe, expect, it } from 'vitest';
import {
  exportTasksToCSV,
  exportTasksToJSON,
  exportTasksToMarkdown,
} from '@/lib/taskExport';
import type { ActionItem } from '@/types/conversation';

function task(overrides: Partial<ActionItem> = {}): ActionItem {
  return {
    id: 'task-1',
    description: 'Ship the thing',
    completed: false,
    ...overrides,
  };
}

describe('exportTasksToCSV', () => {
  it('emits a header row followed by one row per task', () => {
    const csv = exportTasksToCSV([task(), task({ id: 'task-2' })]);
    const lines = csv.split('\n');

    expect(lines[0]).toBe('id,description,due_at,completed,created_at,completed_at');
    expect(lines).toHaveLength(3);
  });

  it('quotes descriptions so a comma cannot shift later columns', () => {
    const csv = exportTasksToCSV([
      task({ description: 'Buy milk, eggs', completed: true }),
    ]);

    expect(csv.split('\n')[1]).toBe('task-1,"Buy milk, eggs",,true,,');
  });

  it('doubles embedded quotes rather than terminating the field', () => {
    const csv = exportTasksToCSV([task({ description: 'Say "hello"' })]);

    expect(csv.split('\n')[1]).toBe('task-1,"Say ""hello""",,false,,');
  });

  it('renders absent optional fields as empty columns', () => {
    const csv = exportTasksToCSV([task()]);

    expect(csv.split('\n')[1]).toBe('task-1,"Ship the thing",,false,,');
  });
});

describe('exportTasksToMarkdown', () => {
  it('marks completed tasks with a checked box', () => {
    const md = exportTasksToMarkdown([
      task({ description: 'Done thing', completed: true }),
      task({ id: 'task-2', description: 'Open thing' }),
    ]);

    expect(md).toBe('- [x] Done thing\n- [ ] Open thing');
  });

  it('omits the due suffix when there is no due date', () => {
    expect(exportTasksToMarkdown([task()])).toBe('- [ ] Ship the thing');
  });
});

describe('exportTasksToJSON', () => {
  it('round-trips the task list', () => {
    const tasks = [task()];

    expect(JSON.parse(exportTasksToJSON(tasks))).toEqual(tasks);
  });
});
