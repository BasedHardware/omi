/**
 * Turn markdown into a one-line plain-text excerpt for meta / OpenGraph
 * descriptions. Kept as plain JS so node:test can import it without a TS loader.
 */

const DEFAULT_MAX_LENGTH = 200;

/**
 * @param {unknown} input
 * @param {number} [maxLength]
 * @returns {string}
 */
export function markdownToPlainText(input, maxLength = DEFAULT_MAX_LENGTH) {
  if (input == null) return '';
  let text = String(input);
  if (!text.trim()) return '';

  // Fenced code: drop the fences, keep the inner text.
  text = text.replace(/```[\w+-]*\n?([\s\S]*?)```/g, '$1');
  text = text.replace(/```+/g, '');

  // Inline code backticks.
  text = text.replace(/`([^`]+)`/g, '$1');
  text = text.replace(/`+/g, '');

  // Images then links: keep alt / link text, drop the URL.
  text = text.replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1');
  text = text.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1');
  text = text.replace(/\[([^\]]+)\]\[[^\]]*\]/g, '$1');

  text = text.replace(/<\/?[^>]+>/g, ' ');

  // Line-oriented markers: headings, blockquotes, bullets, numbered lists.
  text = text.replace(/^#{1,6}\s+/gm, '');
  text = text.replace(/^>\s?/gm, '');
  text = text.replace(/^\s*[-*+]\s+/gm, '');
  text = text.replace(/^\s*\d+\.\s+/gm, '');

  // Emphasis. Underscores only when they are not inside a word (snake_case).
  text = text.replace(/\*\*([^*]+)\*\*/g, '$1');
  text = text.replace(/__([^_]+)__/g, '$1');
  text = text.replace(/\*([^*]+)\*/g, '$1');
  text = text.replace(/(?<!\w)_([^_]+)_(?!\w)/g, '$1');

  text = text.replace(/\s+/g, ' ').trim();
  if (!text) return '';

  if (text.length <= maxLength) return text;

  const slice = text.slice(0, maxLength);
  const lastSpace = slice.lastIndexOf(' ');
  const head = (lastSpace > 0 ? slice.slice(0, lastSpace) : slice).trimEnd();
  return `${head}...`;
}
