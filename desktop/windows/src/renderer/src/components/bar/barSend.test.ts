// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { ChatUsageQuota } from '../../lib/omiApi.generated'
import { createChatQuotaGate } from '../../lib/chatQuotaGate'
import { createBarSender } from './barSend'

// The bar's send path (typed submit AND PTT commit) under the usage-limit gate.
// Asserts the IPC contract: a blocked send never reaches window.omiBar.sendChat,
// and instead notifies the main window (which owns the shared UsageLimitPopup and
// the TTS voice).

// ./firebase is mocked so the sender's signed-in probe never touches the real SDK.
const h = vi.hoisted(() => ({ authObj: { currentUser: null as unknown } }))
vi.mock('../../lib/firebase', () => ({ auth: h.authObj }))

const quota = (over: Partial<ChatUsageQuota> = {}): ChatUsageQuota => ({
  plan: 'Free',
  plan_type: 'basic',
  unit: 'questions',
  used: 0,
  limit: 30,
  percent: 0,
  allowed: true,
  reset_at: null,
  ...over
})

const sendChat = vi.fn()
const notifyUsageLimit = vi.fn()
const notifyAsked = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  h.authObj.currentUser = { uid: 'u1' }
  ;(window as unknown as { omiBar: unknown }).omiBar = { sendChat, notifyUsageLimit }
  ;(window as unknown as { omiOverlay: unknown }).omiOverlay = { notifyAsked }
})

describe('bar send — usage-limit gate', () => {
  it('BLOCKS a send when the quota is exhausted, and raises the limit surface', async () => {
    const sender = createBarSender(createChatQuotaGate(async () => quota({ allowed: false })))
    const notice = await sender.send('are you there', false)

    // The send never reaches the shared chat engine.
    expect(sendChat).not.toHaveBeenCalled()
    expect(notifyAsked).not.toHaveBeenCalled()
    // The main window is told to raise the popup (the bar is a separate renderer
    // and cannot show the shared modal itself). A typed block shows the modal
    // (popup:true) and is not spoken — Mac's typed floating_bar path.
    expect(notifyUsageLimit).toHaveBeenCalledWith({
      message: expect.stringContaining("You've reached"),
      spoken: false,
      popup: true
    })
    // …and the bar renders the same line inline.
    expect(notice).toContain('Upgrade to keep chatting without restrictions.')
  })

  it('BLOCKS a blocked PTT turn: SPEAKS the line but does NOT re-pop the popup (the gesture veto owns it)', async () => {
    // A voice turn only reaches the send gate having slipped past a stale/absent
    // snapshot at the gesture (the pre-capture veto raises the popup when the
    // snapshot already shows the limit). So here we speak the answer but pass
    // popup:false — mirroring macOS's speakOneShot-only voice path, and the reason
    // a refused voice turn can never double-pop the modal.
    const sender = createBarSender(createChatQuotaGate(async () => quota({ allowed: false })))
    await sender.send('what is on my calendar', true)

    expect(sendChat).not.toHaveBeenCalled()
    expect(notifyUsageLimit).toHaveBeenCalledWith({
      message: expect.any(String),
      spoken: true,
      popup: false
    })
  })

  it('lets an in-quota typed send through untouched', async () => {
    const sender = createBarSender(createChatQuotaGate(async () => quota({ used: 3 })))
    const notice = await sender.send('hello', false)

    expect(sendChat).toHaveBeenCalledWith('hello', false)
    expect(notifyAsked).toHaveBeenCalledTimes(1)
    expect(notifyUsageLimit).not.toHaveBeenCalled()
    expect(notice).toBeNull()
  })

  it('lets an in-quota PTT (voice) send through untouched — no PTT regression', async () => {
    const sender = createBarSender(createChatQuotaGate(async () => quota({ used: 3 })))
    await sender.send('remind me tomorrow', true)

    expect(sendChat).toHaveBeenCalledWith('remind me tomorrow', true)
    expect(notifyUsageLimit).not.toHaveBeenCalled()
  })

  it('adds NO network call per send — the reveal sync warms it, sends read the cache', async () => {
    const fetchQuota = vi.fn(async () => quota({ used: 1 }))
    const sender = createBarSender(createChatQuotaGate(fetchQuota))
    await sender.sync()
    await sender.send('one', false)
    await sender.send('two', false)
    await sender.send('three', true)

    expect(sendChat).toHaveBeenCalledTimes(3)
    expect(fetchQuota).toHaveBeenCalledTimes(1)
  })

  it('fails OPEN when the quota fetch errors — a network blip cannot lock the user out', async () => {
    const sender = createBarSender(
      createChatQuotaGate(async () => {
        throw new Error('offline')
      })
    )
    const notice = await sender.send('still there?', false)

    expect(sendChat).toHaveBeenCalledWith('still there?', false)
    expect(notifyUsageLimit).not.toHaveBeenCalled()
    expect(notice).toBeNull()
  })

  it('ignores an empty send without touching the quota or the bridge', async () => {
    const fetchQuota = vi.fn(async () => quota())
    const sender = createBarSender(createChatQuotaGate(fetchQuota))
    expect(await sender.send('   ', false)).toBeNull()

    expect(fetchQuota).not.toHaveBeenCalled()
    expect(sendChat).not.toHaveBeenCalled()
  })

  it('SIGNED OUT: never calls the quota API — an unauthenticated probe would 401 into a spurious "session expired" toast', async () => {
    // Regression: the quota sync (mount + every reveal) is the first authenticated
    // call the bar renderer ever makes. With a dead session the bar is still
    // summonable (`onboarded` survives a forceReauth sign-out), so the GET 401'd →
    // refreshIdToken → forceReauth → a "Your session expired" toast raised FROM the
    // bar. No session ⇒ no quota call, on the reveal sync AND the send path.
    h.authObj.currentUser = null
    const fetchQuota = vi.fn(async () => quota())
    const sender = createBarSender(createChatQuotaGate(fetchQuota))

    await sender.sync()
    await sender.send('hello', false)

    expect(fetchQuota).not.toHaveBeenCalled()
    expect(notifyUsageLimit).not.toHaveBeenCalled()
  })

  it('SIGNED IN: the reveal sync still hits the quota API (the gate is not disabled for a real session)', async () => {
    const fetchQuota = vi.fn(async () => quota({ allowed: false }))
    const sender = createBarSender(createChatQuotaGate(fetchQuota))

    await sender.sync()
    expect(fetchQuota).toHaveBeenCalledTimes(1)
    // …and the synced snapshot still blocks an over-cap send.
    expect(await sender.send('hello', false)).toContain("You've reached")
    expect(sendChat).not.toHaveBeenCalled()
  })

  // checkSync is the PTT pre-capture veto's synchronous read (BarApp → usePushToTalk).
  describe('checkSync — the PTT pre-capture veto seam', () => {
    it('reports the block (with the limit line) once a snapshot is over the cap', async () => {
      const sender = createBarSender(createChatQuotaGate(async () => quota({ allowed: false })))
      await sender.sync()
      expect(sender.checkSync()).toEqual({
        blocked: true,
        message: expect.stringContaining("You've reached")
      })
    })

    it('allows an in-quota snapshot', async () => {
      const sender = createBarSender(createChatQuotaGate(async () => quota({ used: 3 })))
      await sender.sync()
      expect(sender.checkSync()).toEqual({ blocked: false })
    })

    it('SIGNED OUT: never blocks — a signed-out user has no chat to gate', () => {
      h.authObj.currentUser = null
      const fetchQuota = vi.fn(async () => quota({ allowed: false }))
      const sender = createBarSender(createChatQuotaGate(fetchQuota))
      expect(sender.checkSync()).toEqual({ blocked: false })
      // Reads the local snapshot only — never awaits/fetches on the gesture path.
      expect(fetchQuota).not.toHaveBeenCalled()
    })
  })
})
