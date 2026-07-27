/** omi for Even Realities G2.
 *
 *  A five-item home menu on the glasses, backed by a local omi bridge over
 *  WebSocket. Scroll moves the selection, tap opens, double-tap goes back (and
 *  exits from home).
 *
 *  Everything drawn on the glasses is queued through `Display`, which keeps
 *  exactly one SDK call in flight — see `display.ts` for why.
 */
import { AudioInputSource, OsEventTypeList, waitForEvenAppBridge } from '@evenrealities/even_hub_sdk'
import type { EvenHubEvent } from '@evenrealities/even_hub_sdk'
import { onBackgroundRestore, setBackgroundState } from './background-state.ts'
import { BridgeClient } from './bridge-client.ts'
import type { BridgeStatus } from './bridge-client.ts'
import { BANNER_TTL_MS, REQUEST_TIMEOUT_MS, STATUS_CHARS } from './config.ts'
import { Display, serialize } from './display.ts'
import { clampPage, paginate } from './paginate.ts'
import type { ActionItem, InboundMessage, MemoryItem } from './protocol.ts'

// ------------------------------------------------------------------- state

type View = 'home' | 'chat' | 'memories' | 'actions' | 'today'
/** Views a menu row can open — home is the menu itself, so it is never a target. */
type MenuTarget = Exclude<View, 'home'> | 'capture'

/** Menu rows, in order. The last row's label depends on `captureOn`. */
const MENU: Array<{ label: string; view: MenuTarget }> = [
  { label: 'Ask Omi', view: 'chat' },
  { label: 'Memories', view: 'memories' },
  { label: 'Action items', view: 'actions' },
  { label: 'Today', view: 'today' },
  { label: 'Capture', view: 'capture' },
]

/**
 * The glasses have no keyboard and the bridge protocol carries text, not audio,
 * so questions come from a fixed ring: tapping in the chat view asks the next
 * one. Wiring the glasses mic to speech-to-text needs an audio message type the
 * bridge contract does not define yet.
 */
const PROMPTS = [
  'What should I focus on right now?',
  'Summarise my last conversation.',
  'What did I commit to today?',
  'Anything I am forgetting?',
]

let view: View = 'home'
let homeIndex = 0
let captureOn = false
/** Paginated body of whichever read/chat view is open. */
let pages: string[] = ['']
let pageIndex = 0
let promptIndex = 0
let chatQuestion = ''
let chatAnswer = ''
let chatStreaming = false
let chatHistory: Array<{ q: string; a: string }> = []
let banner = ''
let bannerAt = 0

// Registered before anything can mutate the variables above, so the host always
// has a valid snapshot to migrate into the headless WebView.
setBackgroundState('omi', () => ({
  view,
  homeIndex,
  captureOn,
  pages: [...pages],
  pageIndex,
  promptIndex,
  chatQuestion,
  chatAnswer,
  chatHistory: chatHistory.map((entry) => ({ ...entry })),
}))

onBackgroundRestore('omi', (saved) => {
  const s = saved as Partial<{
    view: View
    homeIndex: number
    captureOn: boolean
    pages: string[]
    pageIndex: number
    promptIndex: number
    chatQuestion: string
    chatAnswer: string
    chatHistory: Array<{ q: string; a: string }>
  }>
  view = s.view ?? view
  homeIndex = s.homeIndex ?? homeIndex
  captureOn = s.captureOn ?? captureOn
  pages = s.pages ?? pages
  pageIndex = s.pageIndex ?? pageIndex
  promptIndex = s.promptIndex ?? promptIndex
  chatQuestion = s.chatQuestion ?? chatQuestion
  chatAnswer = s.chatAnswer ?? chatAnswer
  chatHistory = s.chatHistory ?? chatHistory
  // A stream cannot survive the migration — the socket is gone with the old
  // WebView — so the restored view shows whatever text had arrived.
  chatStreaming = false
  void renderCurrentView()
})

// ------------------------------------------------------------------ helpers

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

function truncate(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, max - 1)}…`
}

function menuLabels(): string[] {
  return MENU.map((entry) => (entry.view === 'capture' ? `Capture: ${captureOn ? 'on' : 'off'}` : entry.label))
}

function pageHint(): string {
  return `p ${pageIndex + 1}/${pages.length}`
}

function statusLine(): string {
  if (banner && Date.now() - bannerAt < BANNER_TTL_MS) return truncate(`* ${banner}`, STATUS_CHARS)
  if (client.status() !== 'online') return truncate(`bridge offline - retrying ${client.endpoint()}`, STATUS_CHARS)
  if (view === 'home') return 'scroll move | tap open | double-tap exit'
  if (view === 'chat') {
    return chatStreaming ? `thinking... ${pageHint()}` : `${pageHint()} | tap next question | 2-tap back`
  }
  return `${pageHint()} | scroll page | double-tap back`
}

/** Body text for the current view: the selected page, plus the question when
 *  the chat view is open. */
function bodyText(): string {
  if (view === 'chat') {
    const head = `Q: ${chatQuestion}`
    const page = pages[pageIndex] ?? ''
    return page.length > 0 ? `${head}\n\n${page}` : `${head}\n\n...`
  }
  return pages[pageIndex] ?? ''
}

function setPages(text: string): void {
  pages = paginate(text)
  pageIndex = clampPage(pageIndex, pages.length)
}

// --------------------------------------------------------- render scheduling

// Chat deltas can arrive far faster than the glasses can redraw. Rather than
// queueing an upgrade per delta, mark the body dirty and let one loop coalesce
// them — the last write always wins because the loop re-checks after rendering.
const BODY_MIN_INTERVAL_MS = 150

let bodyDirty = false
let bodyRendering = false
let statusDirty = false
let statusRendering = false

function markBodyDirty(): void {
  bodyDirty = true
  void flushBody()
}

async function flushBody(): Promise<void> {
  if (bodyRendering) return
  bodyRendering = true
  try {
    while (bodyDirty) {
      bodyDirty = false
      try {
        const text = bodyText()
        // Logged here rather than in Display so the line names the view — the
        // verify harness needs to tell a chat repaint from a memories repaint.
        if (await display.setBody(text)) console.log(`[app] rendered ${view} body (${text.length} chars)`)
      } catch (error) {
        console.error('[app] body render failed:', error)
      }
      if (!bodyDirty) break
      await sleep(BODY_MIN_INTERVAL_MS)
    }
  } finally {
    bodyRendering = false
  }
}

function markStatusDirty(): void {
  statusDirty = true
  void flushStatus()
}

async function flushStatus(): Promise<void> {
  if (statusRendering) return
  statusRendering = true
  try {
    while (statusDirty) {
      statusDirty = false
      try {
        await display.setStatus(statusLine())
      } catch (error) {
        console.error('[app] status render failed:', error)
      }
      if (!statusDirty) break
      await sleep(BODY_MIN_INTERVAL_MS)
    }
  } finally {
    statusRendering = false
  }
}

/** Rebuild the page into the layout the current view needs. Flickers, so it is
 *  only used when the layout actually changes. */
async function renderCurrentView(): Promise<void> {
  try {
    if (view === 'home') {
      await display.showHome(menuLabels(), statusLine())
    } else {
      await display.showDetail(bodyText(), statusLine())
    }
    console.log(`[app] view=${view}`)
  } catch (error) {
    console.error('[app] render failed:', error)
  }
}

// ------------------------------------------------------------ bridge traffic

/** The request the open view is waiting on, so a late or missing reply turns
 *  into a visible message instead of a permanent "Loading". */
let pending: { view: View; timer: ReturnType<typeof setTimeout> } | null = null

function clearPending(): void {
  if (pending) clearTimeout(pending.timer)
  pending = null
}

function startPending(target: View): void {
  clearPending()
  const timer = setTimeout(() => {
    if (view !== target) return
    pending = null
    console.warn(`[app] request for ${target} timed out`)
    setPages('No answer from the bridge.\n\nDouble-tap to go back, then try again.')
    markBodyDirty()
    markStatusDirty()
  }, REQUEST_TIMEOUT_MS)
  pending = { view: target, timer }
}

function formatMemories(items: MemoryItem[]): string {
  if (items.length === 0) return 'No memories yet.'
  return items.map((item, index) => `${index + 1}. ${item.content}`).join('\n')
}

function formatActionItems(items: ActionItem[]): string {
  if (items.length === 0) return 'No action items.'
  return items.map((item) => `${item.completed ? '[x]' : '[ ]'} ${item.description}`).join('\n')
}

function onBridgeMessage(message: InboundMessage): void {
  switch (message.type) {
    case 'push':
      // Banners are advisory: they take over the status strip for a while and
      // never disturb whatever view the user is in.
      banner = message.text
      bannerAt = Date.now()
      console.log(`[app] push banner: ${truncate(message.text, 60)}`)
      markStatusDirty()
      setTimeout(markStatusDirty, BANNER_TTL_MS + 100)
      break

    case 'chat_delta':
      if (view !== 'chat') return
      clearPending()
      chatAnswer += message.text
      setPages(chatAnswer)
      // Follow the tail while the answer streams in, like a terminal.
      pageIndex = pages.length - 1
      console.log(`[app] chat delta (+${message.text.length}, total ${chatAnswer.length})`)
      markBodyDirty()
      markStatusDirty()
      break

    case 'chat_done':
      if (view !== 'chat') return
      clearPending()
      // The final frame is authoritative — it repairs any delta that was
      // dropped or arrived out of order.
      chatAnswer = message.text
      chatStreaming = false
      setPages(chatAnswer)
      pageIndex = pages.length - 1
      chatHistory.push({ q: chatQuestion, a: chatAnswer })
      console.log(`[app] chat done (${chatAnswer.length} chars, ${pages.length} page(s))`)
      markBodyDirty()
      markStatusDirty()
      break

    case 'memories':
      if (view !== 'memories') return
      clearPending()
      pageIndex = 0
      setPages(formatMemories(message.items))
      console.log(`[app] memories loaded (${message.items.length} item(s), ${pages.length} page(s))`)
      markBodyDirty()
      markStatusDirty()
      break

    case 'action_items':
      if (view !== 'actions') return
      clearPending()
      pageIndex = 0
      setPages(formatActionItems(message.items))
      console.log(`[app] action items loaded (${message.items.length} item(s), ${pages.length} page(s))`)
      markBodyDirty()
      markStatusDirty()
      break

    case 'today':
      if (view !== 'today') return
      clearPending()
      pageIndex = 0
      setPages(message.text)
      console.log(`[app] today loaded (${pages.length} page(s))`)
      markBodyDirty()
      markStatusDirty()
      break
  }
}

function onBridgeStatus(status: BridgeStatus): void {
  console.log(`[app] bridge status=${status}`)
  markStatusDirty()
}

const client = new BridgeClient({ onMessage: onBridgeMessage, onStatus: onBridgeStatus })

// -------------------------------------------------------------- navigation

async function openRead(target: Exclude<View, 'home' | 'chat'>): Promise<void> {
  view = target
  pageIndex = 0
  setPages('Loading...')
  await renderCurrentView()

  const sent =
    target === 'memories'
      ? client.send({ type: 'memories', limit: 20 })
      : target === 'actions'
        ? client.send({ type: 'action_items' })
        : client.send({ type: 'today' })

  if (sent) {
    startPending(target)
  } else {
    setPages('Bridge offline.\n\nStart the omi bridge on your computer, then double-tap to go back and retry.')
    markBodyDirty()
    markStatusDirty()
  }
}

async function askOmi(): Promise<void> {
  view = 'chat'
  chatQuestion = PROMPTS[promptIndex % PROMPTS.length]
  chatAnswer = ''
  chatStreaming = true
  pageIndex = 0
  setPages('')
  await renderCurrentView()

  if (client.send({ type: 'chat', text: chatQuestion })) {
    console.log(`[app] asked: ${chatQuestion}`)
    startPending('chat')
  } else {
    chatStreaming = false
    setPages('Bridge offline.\n\nStart the omi bridge on your computer, then tap to retry.')
    markBodyDirty()
    markStatusDirty()
  }
}

async function toggleCapture(): Promise<void> {
  const next = !captureOn
  try {
    await serialize('audioControl', () => bridge.audioControl(next, AudioInputSource.Glasses))
    // Only flip the label once the mic actually flipped, so the menu never
    // claims to be capturing when it is not.
    captureOn = next
    console.log(`[app] capture=${captureOn ? 'on' : 'off'}`)
  } catch (error) {
    console.error('[app] audioControl failed:', error)
    banner = 'Microphone unavailable'
    bannerAt = Date.now()
  }
  // List items cannot be updated in place, so the changed label needs a rebuild.
  await renderCurrentView()
}

async function goHome(): Promise<void> {
  clearPending()
  view = 'home'
  await renderCurrentView()
}

function movePage(delta: number): void {
  const next = clampPage(pageIndex + delta, pages.length)
  if (next === pageIndex) return
  pageIndex = next
  console.log(`[app] page=${pageIndex + 1}/${pages.length}`)
  markBodyDirty()
  markStatusDirty()
}

function moveHomeSelection(delta: number): void {
  const count = MENU.length
  const next = (homeIndex + delta + count) % count
  if (next === homeIndex) return
  homeIndex = next
  console.log(`[app] home index=${homeIndex} (${menuLabels()[homeIndex]})`)
  // The OS list draws its own highlight, so there is nothing to redraw here —
  // rebuilding on every scroll would flicker the whole page.
  markStatusDirty()
}

async function selectHomeItem(): Promise<void> {
  const entry = MENU[homeIndex]
  console.log(`[app] select ${entry.view}`)
  switch (entry.view) {
    case 'chat':
      await askOmi()
      break
    case 'capture':
      await toggleCapture()
      break
    default:
      await openRead(entry.view)
      break
  }
}

// ----------------------------------------------------------- input decoding

type Gesture = 'click' | 'double' | 'up' | 'down'

function gestureFromEventType(eventType: OsEventTypeList | undefined): Gesture | null {
  switch (eventType) {
    // The host omits eventType for a plain tap, so an undefined type is a
    // click rather than something to drop.
    case undefined:
    case OsEventTypeList.CLICK_EVENT:
      return 'click'
    case OsEventTypeList.SCROLL_TOP_EVENT:
      return 'up'
    case OsEventTypeList.SCROLL_BOTTOM_EVENT:
      return 'down'
    case OsEventTypeList.DOUBLE_CLICK_EVENT:
      return 'double'
    default:
      return null
  }
}

/**
 * Touch input arrives on whichever channel the host feels like using: tap and
 * double-tap come through `sysEvent`, scroll over a text container comes
 * through `textEvent`, and a list container reports through `listEvent`. Read
 * all three so one build works everywhere.
 *
 * Two absent-means-default traps, both from proto3 dropping zero values:
 *  - an absent `eventType` is `CLICK_EVENT`, not "no gesture";
 *  - an absent `currentSelectItemIndex` is row 0, not "unknown row".
 * Verified against the simulator on SDK 0.0.12 — scrolling a list emits no
 * event at all (the OS moves its own highlight) and the index only shows up on
 * the click that follows, so treating it as unknown would strand the app on
 * whichever row it last saw.
 */
function decode(event: EvenHubEvent): { gesture: Gesture; listIndex?: number } | null {
  if (event.listEvent) {
    const gesture = gestureFromEventType(event.listEvent.eventType)
    if (!gesture) return null
    return { gesture, listIndex: event.listEvent.currentSelectItemIndex ?? 0 }
  }
  if (event.textEvent) {
    const gesture = gestureFromEventType(event.textEvent.eventType)
    return gesture ? { gesture } : null
  }
  if (event.sysEvent) {
    const gesture = gestureFromEventType(event.sysEvent.eventType)
    return gesture ? { gesture } : null
  }
  return null
}

async function handleGesture(gesture: Gesture, listIndex?: number): Promise<void> {
  if (view === 'home') {
    // When the host owns the list highlight it also reports the resulting
    // index; trust it over the local counter so the two never drift.
    if (typeof listIndex === 'number' && listIndex >= 0 && listIndex < MENU.length) {
      if (listIndex !== homeIndex) {
        homeIndex = listIndex
        console.log(`[app] home index=${homeIndex} (${menuLabels()[homeIndex]})`)
        markStatusDirty()
      }
    }

    switch (gesture) {
      case 'up':
        if (listIndex === undefined) moveHomeSelection(-1)
        break
      case 'down':
        if (listIndex === undefined) moveHomeSelection(1)
        break
      case 'click':
        await selectHomeItem()
        break
      case 'double':
        console.log('[app] exit requested')
        await display.requestExit()
        break
    }
    return
  }

  switch (gesture) {
    case 'up':
      movePage(-1)
      break
    case 'down':
      movePage(1)
      break
    case 'click':
      // Only the chat view has something to do with a tap: ask the next
      // question in the ring. Read views ignore it.
      if (view === 'chat' && !chatStreaming) {
        promptIndex = (promptIndex + 1) % PROMPTS.length
        await askOmi()
      }
      break
    case 'double':
      await goHome()
      break
  }
}

// -------------------------------------------------------------------- boot

const bridge = await waitForEvenAppBridge()
console.log('[app] bridge ready')

const display = new Display(bridge)

client.connect()

await display.createStartUpPage(menuLabels(), statusLine())

// A background restore can land before or after the start-up page exists. If
// it already moved us off the home view, rebuild into the right layout now.
if (view !== 'home') await renderCurrentView()

// Serialize gesture handling too: two overlapping handlers could interleave
// rebuilds and leave the display showing one view's body under another's list.
let inputChain: Promise<void> = Promise.resolve()

bridge.onEvenHubEvent((event) => {
  const decoded = decode(event)
  if (!decoded) return
  console.log(`[app] gesture=${decoded.gesture}${decoded.listIndex === undefined ? '' : ` index=${decoded.listIndex}`}`)
  inputChain = inputChain
    .then(() => handleGesture(decoded.gesture, decoded.listIndex))
    .catch((error) => console.error('[app] gesture failed:', error))
})

console.log('[app] ready')
