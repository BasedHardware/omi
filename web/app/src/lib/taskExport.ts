import type { ActionItem } from '@/types/conversation';

/**
 * Export tasks to CSV format
 */
export function exportTasksToCSV(tasks: ActionItem[]): string {
  const headers = ['id', 'description', 'due_at', 'completed', 'created_at', 'completed_at'];
  const rows = tasks.map(t => [
    t.id,
    `"${t.description.replace(/"/g, '""')}"`, // Escape quotes in CSV
    t.due_at || '',
    t.completed ? 'true' : 'false',
    t.created_at || '',
    t.completed_at || '',
  ]);
  return [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
}

/**
 * Export tasks to JSON format
 */
export function exportTasksToJSON(tasks: ActionItem[]): string {
  return JSON.stringify(tasks, null, 2);
}

/**
 * Export tasks to Markdown checklist format
 */
export function exportTasksToMarkdown(tasks: ActionItem[]): string {
  return tasks
    .map(t => {
      const checkbox = t.completed ? '[x]' : '[ ]';
      const due = t.due_at
        ? ` (due: ${new Date(t.due_at).toLocaleDateString()})`
        : '';
      return `- ${checkbox} ${t.description}${due}`;
    })
    .join('\n');
}

/**
 * Copy tasks to clipboard as plain text
 */
export async function copyTasksToClipboard(tasks: ActionItem[]): Promise<void> {
  const text = tasks
    .map(t => {
      const status = t.completed ? '[DONE] ' : '';
      const due = t.due_at
        ? ` - Due: ${new Date(t.due_at).toLocaleDateString()}`
        : '';
      return `${status}${t.description}${due}`;
    })
    .join('\n');

  await navigator.clipboard.writeText(text);
}

/**
 * Download a file with the given content
 */
export function downloadFile(
  content: string,
  filename: string,
  mimeType: string
): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Export and download tasks in the specified format
 */
export function downloadTasks(
  tasks: ActionItem[],
  format: 'csv' | 'json' | 'markdown'
): void {
  const timestamp = new Date().toISOString().split('T')[0];

  switch (format) {
    case 'csv':
      downloadFile(
        exportTasksToCSV(tasks),
        `tasks-${timestamp}.csv`,
        'text/csv'
      );
      break;
    case 'json':
      downloadFile(
        exportTasksToJSON(tasks),
        `tasks-${timestamp}.json`,
        'application/json'
      );
      break;
    case 'markdown':
      downloadFile(
        exportTasksToMarkdown(tasks),
        `tasks-${timestamp}.md`,
        'text/markdown'
      );
      break;
  }
}
