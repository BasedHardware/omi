import { presentableNoteTitle } from '@omi/note-shared/note-sources.mjs';
import type { Element, Root, RootContent } from 'hast';

export interface ChatCitationSource {
  id: string;
  title: string;
  emoji: string;
  href: string;
}

export interface ChatCitationMemoryInput {
  id?: string | null;
  structured?: {
    title?: string | null;
    emoji?: string | null;
  } | null;
}

export function chatCitationHref(conversationId: string): string {
  return `/conversations?id=${encodeURIComponent(conversationId)}`;
}

/**
 * Normalize the server's resolved `memories` conversation cards in first-mention
 * order, dropping malformed or duplicate entries.
 */
export function normalizeChatCitations(
  memories?: readonly (ChatCitationMemoryInput | null | undefined)[] | null,
): ChatCitationSource[] {
  if (!Array.isArray(memories)) return [];
  const sources: ChatCitationSource[] = [];
  const seen = new Set<string>();
  for (const item of memories) {
    if (!item || typeof item.id !== 'string') continue;
    const id = item.id.trim();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    // Display repair for legacy titles (`[s01234]`, `Speaker_00`); cards carry no transcript.
    const title =
      typeof item.structured?.title === 'string'
        ? presentableNoteTitle(item.structured.title).trim() || 'Untitled conversation'
        : 'Untitled conversation';
    const emoji =
      typeof item.structured?.emoji === 'string' && item.structured.emoji.trim()
        ? item.structured.emoji.trim()
        : '📝';
    sources.push({
      id,
      title,
      emoji,
      href: chatCitationHref(id),
    });
  }
  return sources;
}

/** Sweep prose after Markdown parsing and sanitization have protected code and links. */
export function chatCitationLinks({ memories }: { memories: readonly { id: string }[] }) {
  return (root: Root) => {
    function visit(node: Root | Element) {
      if (
        'tagName' in node &&
        ['a', 'code', 'pre', 'script', 'style'].includes(node.tagName)
      )
        return;
      const children: RootContent[] = [];
      for (const child of node.children) {
        if (child.type !== 'text') {
          if (child.type === 'element') visit(child);
          children.push(child);
          continue;
        }
        // Same marker/list separators as the server strip grammar, applied only to prose.
        const list = String.raw`#?\s*\d+(?:\s*[,;–-]\s*#?\s*\d+)*`;
        const pattern = new RegExp(
          String.raw`\[\s*(?:\^\s*)?(${list})\s*\]|【\s*(${list})\s*】`,
          'g',
        );
        let start = 0;
        for (const match of child.value.matchAll(pattern)) {
          const content = match[1] ?? match[2];
          const ordinals = [...content.matchAll(/#?\s*(\d+)/g)];
          if (match.index > start)
            children.push({ type: 'text', value: child.value.slice(start, match.index) });
          // Unresolved ordinals are debris. Emit only resolved markers, with separators
          // between actual links so a mixed list cannot leave dangling punctuation.
          let emitted = false;
          for (const ordinal of ordinals) {
            const index = Number(ordinal[1]);
            if (!Number.isSafeInteger(index) || !memories[index - 1]?.id) continue;
            if (emitted) children.push({ type: 'text', value: ', ' });
            children.push({
              type: 'element',
              tagName: 'a',
              properties: {
                href: chatCitationHref(memories[index - 1].id),
                dataChatCitation: index,
              },
              children: [{ type: 'text', value: String(index) }],
            });
            emitted = true;
          }
          start = match.index + match[0].length;
        }
        if (start < child.value.length)
          children.push({ type: 'text', value: child.value.slice(start) });
      }
      node.children = children;
    }
    visit(root);
  };
}
