import type { Memory } from '@/types/conversation';

/**
 * Export memories to CSV format
 */
export function exportMemoriesToCSV(memories: Memory[]): string {
  const headers = ['id', 'content', 'category', 'tags', 'created_at', 'updated_at'];
  const rows = memories.map(m => [
    m.id,
    `"${m.content.replace(/"/g, '""')}"`, // Escape quotes in CSV
    m.category,
    `"${m.tags.join(', ')}"`,
    m.created_at || '',
    m.updated_at || '',
  ]);
  return [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
}

/**
 * Export memories to JSON format
 */
export function exportMemoriesToJSON(memories: Memory[]): string {
  return JSON.stringify(memories, null, 2);
}

/**
 * Export memories to Markdown format
 */
export function exportMemoriesToMarkdown(memories: Memory[]): string {
  return memories
    .map(m => {
      const tags = m.tags.length > 0 ? ` [${m.tags.join(', ')}]` : '';
      const date = m.created_at
        ? new Date(m.created_at).toLocaleDateString()
        : '';
      return `## ${m.category}${tags}\n\n${m.content}\n\n_${date}_\n`;
    })
    .join('\n---\n\n');
}

/**
 * Copy memories to clipboard as plain text
 */
export async function copyMemoriesToClipboard(memories: Memory[]): Promise<void> {
  const text = memories
    .map(m => {
      const tags = m.tags.length > 0 ? ` [${m.tags.join(', ')}]` : '';
      return `[${m.category}]${tags}\n${m.content}`;
    })
    .join('\n\n---\n\n');

  await navigator.clipboard.writeText(text);
}

/**
 * Download a file with the given content
 */
function downloadFile(
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
 * Export and download memories in the specified format
 */
export function downloadMemories(
  memories: Memory[],
  format: 'csv' | 'json' | 'markdown'
): void {
  const timestamp = new Date().toISOString().split('T')[0];

  switch (format) {
    case 'csv':
      downloadFile(
        exportMemoriesToCSV(memories),
        `memories-${timestamp}.csv`,
        'text/csv'
      );
      break;
    case 'json':
      downloadFile(
        exportMemoriesToJSON(memories),
        `memories-${timestamp}.json`,
        'application/json'
      );
      break;
    case 'markdown':
      downloadFile(
        exportMemoriesToMarkdown(memories),
        `memories-${timestamp}.md`,
        'text/markdown'
      );
      break;
  }
}
