import { describe, it, expect, vi } from 'vitest'
import { ChatTaskQueue } from './chatTaskQueue'

function gate(): { promise: Promise<void>; open: () => void } {
  let open!: () => void
  const promise = new Promise<void>((r) => (open = r))
  return { promise, open }
}

describe('ChatTaskQueue', () => {
  it('runs a message arriving mid-generation after the current one (regression: two rapid events used to drop the second)', async () => {
    const q = new ChatTaskQueue()
    const firstReply = gate()
    const ran: string[] = []

    // Two rapid message.upserted events for the same chat: m2 lands while m1's
    // reply is still generating.
    q.submit('chat1', async () => {
      await firstReply.promise
      ran.push('m1')
    })
    q.submit('chat1', async () => {
      ran.push('m2')
    })

    expect(ran).toEqual([]) // m2 parked — not run early, not dropped
    firstReply.open()
    await vi.waitFor(() => expect(ran).toEqual(['m1', 'm2']))
  })

  it('coalesces parked tasks — only the newest superseding message runs', async () => {
    const q = new ChatTaskQueue()
    const firstReply = gate()
    const ran: string[] = []

    q.submit('chat1', async () => {
      await firstReply.promise
      ran.push('m1')
    })
    q.submit('chat1', async () => {
      ran.push('m2')
    })
    q.submit('chat1', async () => {
      ran.push('m3')
    })

    firstReply.open()
    await vi.waitFor(() => expect(ran).toEqual(['m1', 'm3'])) // m2 superseded by m3
  })

  it('does not serialize across different chats', async () => {
    const q = new ChatTaskQueue()
    const blocked = gate()
    const ran: string[] = []

    q.submit('chat1', async () => {
      await blocked.promise
      ran.push('chat1')
    })
    q.submit('chat2', async () => {
      ran.push('chat2')
    })

    await vi.waitFor(() => expect(ran).toEqual(['chat2'])) // chat2 not stuck behind chat1
    blocked.open()
    await vi.waitFor(() => expect(ran).toEqual(['chat2', 'chat1']))
  })

  it('releases the chat and drains the parked task when a task throws', async () => {
    const q = new ChatTaskQueue()
    const ran: string[] = []

    q.submit('chat1', async () => {
      throw new Error('generation failed')
    })
    q.submit('chat1', async () => {
      ran.push('m2')
    })

    await vi.waitFor(() => expect(ran).toEqual(['m2']))
    // Chat is free again for the next message.
    q.submit('chat1', async () => {
      ran.push('m3')
    })
    await vi.waitFor(() => expect(ran).toEqual(['m2', 'm3']))
  })
})
