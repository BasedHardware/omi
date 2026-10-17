import type { Element, Root, RootContent } from 'hast';

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
        const pattern = /\[(?:#|\^)?(\d+)\]|【(?:#|\^)?(\d+)】/g;
        let start = 0;
        for (const match of child.value.matchAll(pattern)) {
          const index = Number(match[1] ?? match[2]);
          if (!Number.isSafeInteger(index) || !memories[index - 1]?.id) continue;
          if (match.index > start)
            children.push({ type: 'text', value: child.value.slice(start, match.index) });
          children.push({
            type: 'element',
            tagName: 'a',
            properties: {
              href: `/conversations?id=${encodeURIComponent(memories[index - 1].id)}`,
              dataChatCitation: index,
            },
            children: [{ type: 'text', value: String(index) }],
          });
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
