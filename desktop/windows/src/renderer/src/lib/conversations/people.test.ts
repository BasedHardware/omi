import { beforeEach, describe, expect, it, vi } from 'vitest'
import { assignSegmentsBulk } from './people'
import { omiApi } from '../apiClient'

vi.mock('../apiClient', () => ({
  omiApi: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn()
  }
}))

const patchMock = vi.mocked(omiApi.patch)

describe('assignSegmentsBulk', () => {
  beforeEach(() => {
    patchMock.mockReset()
    patchMock.mockResolvedValue({ data: {} } as never)
  })

  it("sends value 'true' for an owner assignment", async () => {
    await assignSegmentsBulk('conv-1', ['seg-a'], { type: 'is_user' })
    expect(patchMock).toHaveBeenCalledWith('/v1/conversations/conv-1/segments/assign-bulk', {
      segment_ids: ['seg-a'],
      assign_type: 'is_user',
      value: 'true'
    })
  })

  it('preserves the person id for a person assignment', async () => {
    await assignSegmentsBulk('conv-1', ['seg-a', 'seg-b'], {
      type: 'person_id',
      personId: 'person-42'
    })
    expect(patchMock).toHaveBeenCalledWith('/v1/conversations/conv-1/segments/assign-bulk', {
      segment_ids: ['seg-a', 'seg-b'],
      assign_type: 'person_id',
      value: 'person-42'
    })
  })

  it('throws on empty segment ids and issues no request', async () => {
    await expect(assignSegmentsBulk('conv-1', [], { type: 'is_user' })).rejects.toThrow(
      'assignSegmentsBulk'
    )
    expect(patchMock).not.toHaveBeenCalled()
  })

  it('propagates network failures', async () => {
    patchMock.mockRejectedValue(new Error('network down'))
    await expect(assignSegmentsBulk('conv-1', ['seg-a'], { type: 'is_user' })).rejects.toThrow(
      'network down'
    )
  })
})
