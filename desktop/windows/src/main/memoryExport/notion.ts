import type { ExportMemory } from '../../shared/types'

// Pinned Notion REST API version (required header). Matches the macOS client.
const NOTION_VERSION = '2022-06-28'
// Notion caps a page-create / append call at 100 child blocks.
const MAX_BLOCKS = 100

// Notion caps a single rich_text item at 2000 characters (UTF-16 code units) and
// a block at 100 rich_text items. Chunk a long memory into <=2000 code-unit pieces
// without splitting a surrogate pair, so neither the per-item char limit nor a
// lone surrogate can break the request.
function richTextChunks(content: string): { type: 'text'; text: { content: string } }[] {
  const out: { type: 'text'; text: { content: string } }[] = []
  let i = 0
  while (i < content.length) {
    let end = Math.min(i + 2000, content.length)
    if (end < content.length) {
      const code = content.charCodeAt(end - 1)
      if (code >= 0xd800 && code <= 0xdbff) end -= 1 // don't cut a surrogate pair
    }
    out.push({ type: 'text', text: { content: content.slice(i, end) } })
    i = end
  }
  if (out.length === 0) out.push({ type: 'text', text: { content: '' } })
  return out
}

function toBlocks(memories: ExportMemory[]): unknown[] {
  const blocks: unknown[] = []
  for (const m of memories) {
    const chunks = richTextChunks(m.content)
    // Notion allows at most 100 rich_text items per block; a very long memory
    // spills into additional bullet blocks rather than being truncated.
    for (let i = 0; i < chunks.length; i += 100) {
      blocks.push({
        object: 'block',
        type: 'bulleted_list_item',
        bulleted_list_item: { rich_text: chunks.slice(i, i + 100) }
      })
    }
  }
  return blocks
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

  // Build all blocks up front, then batch by BLOCK count: a single long memory can
  // now span multiple blocks, so batching by memory count could overflow the
  // 100-block-per-call ceiling.
  const blocks = toBlocks(memories)

  const createRes = await fetch('https://api.notion.com/v1/pages', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      parent: { page_id: parentPageId },
      properties: { title: { title: [{ text: { content: 'Omi Memories' } }] } },
      children: blocks.slice(0, MAX_BLOCKS)
    })
  })
  if (!createRes.ok) {
    throw new Error(`Notion create failed (${createRes.status}): ${await createRes.text()}`)
  }
  const page = (await createRes.json()) as { id: string; url?: string }

  for (let i = MAX_BLOCKS; i < blocks.length; i += MAX_BLOCKS) {
    const res = await fetch(`https://api.notion.com/v1/blocks/${page.id}/children`, {
      method: 'PATCH',
      headers,
      body: JSON.stringify({ children: blocks.slice(i, i + MAX_BLOCKS) })
    })
    if (!res.ok) {
      throw new Error(`Notion append failed (${res.status}): ${await res.text()}`)
    }
  }

  return page.url ?? `https://notion.so/${page.id.replace(/-/g, '')}`
}
