import type { ExportMemory } from '../../shared/types'

// Pinned Notion REST API version (required header). Matches the macOS client.
const NOTION_VERSION = '2022-06-28'
// Notion caps a page-create / append call at 100 child blocks.
const MAX_BLOCKS = 100

// One bulleted-list block per memory. Notion rich_text content is capped at
// 2000 chars per item, so long memories are truncated to stay within the limit.
// Notion caps a single rich_text item at 2000 chars and a block at 100 items.
// Split a long memory into <=2000 code-point chunks (so a surrogate pair is never
// cut) and emit one rich_text item per chunk, rather than dropping the tail.
function richTextChunks(content: string): unknown[] {
  const cps = Array.from(content)
  const out: unknown[] = []
  for (let i = 0; i < cps.length && out.length < 100; i += 2000) {
    out.push({ type: 'text', text: { content: cps.slice(i, i + 2000).join('') } })
  }
  if (out.length === 0) out.push({ type: 'text', text: { content: '' } })
  return out
}

function toBlocks(memories: ExportMemory[]): unknown[] {
  return memories.map((m) => ({
    object: 'block',
    type: 'bulleted_list_item',
    bulleted_list_item: {
      rich_text: richTextChunks(m.content)
    }
  }))
}

// Create an "Omi Memories" page under `parentPageId` and append every memory as
// a bullet, batching at Notion's 100-block ceiling. Returns the new page URL.
// Uses the official Notion REST API with the user's internal-integration token.
export async function exportToNotion(
  token: string,
  parentPageId: string,
  memories: ExportMemory[]
): Promise<string> {
  const headers = {
    Authorization: `Bearer ${token}`,
    'Notion-Version': NOTION_VERSION,
    'Content-Type': 'application/json'
  }

  const createRes = await fetch('https://api.notion.com/v1/pages', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      parent: { page_id: parentPageId },
      properties: { title: { title: [{ text: { content: 'Omi Memories' } }] } },
      children: toBlocks(memories.slice(0, MAX_BLOCKS))
    })
  })
  if (!createRes.ok) {
    throw new Error(`Notion create failed (${createRes.status}): ${await createRes.text()}`)
  }
  const page = (await createRes.json()) as { id: string; url?: string }

  for (let i = MAX_BLOCKS; i < memories.length; i += MAX_BLOCKS) {
    const res = await fetch(`https://api.notion.com/v1/blocks/${page.id}/children`, {
      method: 'PATCH',
      headers,
      body: JSON.stringify({ children: toBlocks(memories.slice(i, i + MAX_BLOCKS)) })
    })
    if (!res.ok) {
      throw new Error(`Notion append failed (${res.status}): ${await res.text()}`)
    }
  }

  return page.url ?? `https://notion.so/${page.id.replace(/-/g, '')}`
}
