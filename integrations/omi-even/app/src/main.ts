/** omi for Even Realities G2.
 *
 *  A six-item home menu on the glasses, backed by a local omi bridge over
 *  WebSocket. Scroll moves the selection, tap opens, double-tap goes back (and
 *  exits from home).
 *
 *  "Ask Omi" dictates: tap to start listening, tap again to ask. The glasses
 *  have no keyboard and no on-device speech recognition for plugins, so the
 *  4-mic array's raw PCM is streamed to the bridge, which transcribes it and
 *  answers. See `ask-recorder.ts` for the microphone lifecycle.
 *
 *  Everything drawn on the glasses is queued through `Display`, which keeps
 *  exactly one SDK call in flight — see `display.ts` for why.
 */
import { AudioInputSource, OsEventTypeList, waitForEvenAppBridge } from '@evenrealities/even_hub_sdk'
import type { EvenHubEvent } from '@evenrealities/even_hub_sdk'
import { AskRecorder } from './ask-recorder.ts'
import { clock, meterBar } from './audio.ts'
import { onBackgroundRestore, setBackgroundState } from './background-state.ts'
import { BridgeClient } from './bridge-client.ts'
import type { BridgeStatus } from './bridge-client.ts'
import { BANNER_TTL_MS, REQUEST_TIMEOUT_MS, STATUS_CHARS } from './config.ts'
import { Display, serialize } from './display.ts'
import { clampPage, paginate } from './paginate.ts'
import type { ActionItem, InboundMessage, MemoryItem } from './protocol.ts'

// ------------------------------------------------------------------- state

type View = 'home' | 'chat' | 'memories' | 'actions' | 'today'
/** Views a menu row can open — home is the menu itself, so it is never a
 *  target. `capture` toggles in place and `suggest` opens the chat view with a
 *  canned question rather than the microphone. */
type MenuTarget = Exclude<View, 'home'> | 'capture' | 'suggest'

/** Menu rows, in order. The Capture row's label depends on `captureOn`. */
const MENU: Array<{ label: string; view: MenuTarget }> = [
  { label: 'Ask Omi', view: 'chat' },
  { label: 'Memories', view: 'memories' },
  { label: 'Action items', view: 'actions' },
  { label: 'Today', view: 'today' },
  { label: 'Capture', view: 'capture' },
  { label: 'Suggestions', view: 'suggest' },
]

/**
 * Canned questions for the Suggestions row. Dictation is the way to ask
 * anything, but a fixed ring still earns its place: it is the only thing that
 * works when the microphone is unavailable, and it is one tap instead of a
 * spoken sentence for the questions asked over and over.
 */
const PROMPTS = [
  'What should I focus on right now?',
  'Summarise my last conversation.',
  'What did I commit to today?',
  'Anything I am forgetting?',
]

/**
 * Where the chat view is in the dictate → transcribe → answer cycle.
 *  - `starting`   the microphone has been asked for but has not opened yet
 *  - `listening`  the microphone is live and PCM is going to the bridge
 *  - `thinking`   audio is in, waiting for the transcript
 *  - `answering`  the transcript is on screen and the answer is streaming
 *  - `idle`       an answer is complete, or the view was opened cold
 *  - `error`      nothing heard, no bridge, or no microphone
 */
type AskPhase = 'starting' | 'listening' | 'thinking' | 'answering' | 'idle' | 'error'

let view: View = 'home'
let homeIndex = 0
let captureOn = false
/** Paginated body of whichever read/chat view is open. */
let pages: string[] = ['']
let pageIndex = 0
let promptIndex = 0
/** Voice dictates the question; suggest picks it off the canned ring. Only the
 *  meaning of a tap differs, so both share the one chat view. */
let askMode: 'voice' | 'suggest' = 'voice'
let askPhase: AskPhase = 'idle'
/** User-facing text for the `error` phase, straight from the bridge when it
 *  sent one. */
let askHint = ''
let chatQuestion = ''
let chatAnswer = ''
let chatHistory: Array<{ q: string; a: string }> = []
let banner = ''
let bannerAt = 0

// Registered before anything can mutate the variables above, so the host always
// has a valid snapshot to migrate into the headless WebView.
setBackgroundState('omi', () => {
  // Going to the background tears down this WebView and with it the socket the
  // audio was going to. Release the microphone on the way out — best effort,
  // since nothing can be awaited here.
  if (recorder.isListening()) recorder.teardown()
  return {
    view,
    homeIndex,
    captureOn,
    pages: [...pages],
    pageIndex,
    promptIndex,
    askMode,
    // Never restore into a live-microphone phase: the restored WebView has no
    // microphone open and no socket, so it would be claiming to listen.
    askPhase: askPhase === 'starting' || askPhase === 'listening' || askPhase === 'thinking' ? 'idle' : askPhase,
    askHint,
    chatQuestion,
    chatAnswer,
    chatHistory: chatHistory.map((entry) => ({ ...entry })),
  }
})

onBackgroundRestore('omi', (saved) => {
  const s = saved as Partial<{
    view: View
    homeIndex: number
    captureOn: boolean
    pages: string[]
    pageIndex: number
    promptIndex: number
    askMode: 'voice' | 'suggest'
    askPhase: AskPhase
    askHint: string
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
  askMode = s.askMode ?? askMode
  askPhase = s.askPhase ?? askPhase
  askHint = s.askHint ?? askHint
  chatQuestion = s.chatQuestion ?? chatQuestion
  chatAnswer = s.chatAnswer ?? chatAnswer
  chatHistory = s.chatHistory ?? chatHistory
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
  if (view === 'chat') return truncate(chatStatus(), STATUS_CHARS)
  return `${pageHint()} | scroll page | double-tap back`
}

function chatStatus(): string {
  switch (askPhase) {
    case 'starting':
      return 'opening the mic... | 2-tap cancel'
    case 'listening':
      return `rec ${clock(recorder.elapsedMs())}/${clock(recorder.capMs())} | tap ask | 2-tap cancel`
    case 'thinking':
      return 'transcribing... | 2-tap back'
    case 'answering':
      return `${pageHint()} | answering... | 2-tap back`
    case 'error':
      return 'tap to retry | 2-tap back'
    case 'idle':
      return askMode === 'voice'
        ? `${pageHint()} | tap to ask again | 2-tap back`
        : `${pageHint()} | tap next question | 2-tap back`
  }
}

/** Body text for the current view: the selected page, plus the question when
 *  the chat view is showing an answer. */
function bodyText(): string {
  if (view !== 'chat') return pages[pageIndex] ?? ''

  switch (askPhase) {
    case 'starting':
      return 'Starting microphone...'
    case 'listening':
      // The meter is the point: a bar that moves with the user's voice is the
      // only proof on a screen this small that the microphone is really live.
      return `Listening...\n\n${meterBar(recorder.level())}\n\nTap to ask. Double-tap to cancel.`
    case 'thinking':
      return 'Thinking...'
    case 'error':
      return askHint || 'Something went wrong. Tap to retry.'
    default: {
      const head = `Q: ${chatQuestion}`
      const page = pages[pageIndex] ?? ''
      return page.length > 0 ? `${head}\n\n${page}` : `${head}\n\n...`
    }
  }
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
let lastBodyHead = ''

/** Log the first line of whatever just went to the display. Cheap, low volume
 *  (it only fires when the line changes), and it is the only way a test — or a
 *  bug report — can tell what the user was actually looking at. */
function logBodyHead(text: string): void {
  const head = text.split('\n', 1)[0] ?? ''
  if (head === lastBodyHead) return
  lastBodyHead = head
  console.log(`[app] body head: ${head}`)
}

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
        if (await display.setBody(text)) {
          console.log(`[app] rendered ${view} body (${text.length} chars)`)
          logBodyHead(text)
        }
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
      // A rebuilt list comes back with the OS highlight on row 0. Mirror that
      // or the app's idea of the selected row drifts from the display's —
      // which is what happens after the Capture row relabels itself.
      homeIndex = 0
    } else {
      const body = bodyText()
      await display.showDetail(body, statusLine())
      logBodyHead(body)
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
    if (target === 'chat') {
      askPhase = 'error'
      askHint = 'No answer from the bridge.\n\nTap to retry.'
    } else {
      setPages('No answer from the bridge.\n\nDouble-tap to go back, then try again.')
    }
    markBodyDirty()
    markStatusDirty()
  }, REQUEST_TIMEOUT_MS)
  pending = { view: target, timer }
}

/**
 * Answers to questions the user cancelled. The bridge has no request ids and
 * handles one ask at a time per socket, so counting the responses still owed
 * is enough to drop them: a cancel that got `ask_stop` out will still be
 * transcribed and answered, and that answer must not land on the next question.
 */
let staleAsks = 0

function dropStaleResponse(terminal: boolean): boolean {
  if (staleAsks <= 0) return false
  if (terminal) {
    staleAsks--
    console.log(`[app] discarded a cancelled ask response (${staleAsks} still owed)`)
  }
  return true
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

    case 'ask_listening':
      // Confirmation that the bridge opened its buffer. The display already
      // says "Listening" — this is here so a one-sided socket is diagnosable.
      console.log('[app] bridge is buffering the question')
      break

    case 'transcribed':
      if (dropStaleResponse(false)) return
      if (view !== 'chat') return
      clearPending()
      if (message.text.trim().length === 0) {
        // Defence in depth: the bridge sends `ask_error` for this, but an
        // empty question must never reach Omi.
        askPhase = 'error'
        askHint = "Didn't catch that. Tap to retry."
        console.warn('[app] empty transcript')
      } else {
        chatQuestion = message.text
        chatAnswer = ''
        askPhase = 'answering'
        pageIndex = 0
        setPages('')
        console.log(`[app] transcript: ${truncate(message.text, 80)}`)
      }
      // Keep the request alive: the transcript is only half the answer.
      if (askPhase === 'answering') startPending('chat')
      markBodyDirty()
      markStatusDirty()
      break

    case 'ask_error':
      if (dropStaleResponse(true)) return
      if (view !== 'chat') return
      clearPending()
      askPhase = 'error'
      askHint = message.text
      console.warn(`[app] ask error: ${message.text}`)
      markBodyDirty()
      markStatusDirty()
      break

    case 'chat_delta':
      if (dropStaleResponse(false)) return
      if (view !== 'chat') return
      // A delta while the microphone is live belongs to a question that was
      // already abandoned; taking it would overwrite the listening screen.
      if (askPhase === 'starting' || askPhase === 'listening') return
      clearPending()
      askPhase = 'answering'
      chatAnswer += message.text
      setPages(chatAnswer)
      // Follow the tail while the answer streams in, like a terminal.
      pageIndex = pages.length - 1
      console.log(`[app] chat delta (+${message.text.length}, total ${chatAnswer.length})`)
      markBodyDirty()
      markStatusDirty()
      break

    case 'chat_done':
      if (dropStaleResponse(true)) return
      if (view !== 'chat') return
      if (askPhase === 'starting' || askPhase === 'listening') return
      clearPending()
      // The final frame is authoritative — it repairs any delta that was
      // dropped or arrived out of order.
      chatAnswer = message.text
      askPhase = 'idle'
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
  // A question being dictated into a socket that just died is dead air, and
  // the microphone would stay open until the 20s cap for nothing.
  if (status !== 'online' && recorder.isListening()) {
    enqueue(() => abortListening('Lost the bridge.\n\nTap to retry once it is back.'))
  }
  markStatusDirty()
}

const client = new BridgeClient({ onMessage: onBridgeMessage, onStatus: onBridgeStatus })

// ---------------------------------------------------------------- microphone

/**
 * The glasses have one microphone and two features that want it: continuous
 * Capture, and a question being dictated. Both go through here, so whichever
 * one stops first cannot switch the other one off underneath it.
 */
let micOn = false
let askWantsMic = false

async function applyMic(): Promise<boolean> {
  const wanted = captureOn || askWantsMic
  if (wanted === micOn) return true
  try {
    await serialize('audioControl', () =>
      wanted ? bridge.audioControl(true, AudioInputSource.Glasses) : bridge.audioControl(false),
    )
    micOn = wanted
    console.log(`[app] audioControl(${wanted ? 'true, glasses' : 'false'}) ok - mic=${wanted ? 'on' : 'off'}`)
    return true
  } catch (error) {
    console.error('[app] audioControl failed:', error)
    return false
  }
}

const recorder = new AskRecorder({
  sendJson: (message) => client.send(message),
  sendBinary: (pcm) => client.sendBinary(pcm),
  setMic: (on) => {
    askWantsMic = on
    return applyMic()
  },
  onUpdate: () => {
    if (view === 'chat' && askPhase === 'listening') {
      markBodyDirty()
      markStatusDirty()
    }
  },
  onCap: () => enqueue(() => stopAndAsk('cap')),
})

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

/** Open the chat view and start dictating. */
async function startListening(): Promise<void> {
  const rebuild = view !== 'chat'
  view = 'chat'
  askMode = 'voice'
  askPhase = 'starting'
  askHint = ''
  chatQuestion = ''
  chatAnswer = ''
  pageIndex = 0
  setPages('')
  clearPending()

  // "Starting microphone" and not "Listening": opening the mic is a round trip
  // to the glasses, and claiming to listen before it lands is the one thing
  // this screen must never do.
  if (rebuild) await renderCurrentView()
  else markBodyDirty()

  const started = await recorder.start()
  if (!started.ok) {
    askPhase = 'error'
    askHint =
      started.reason === 'offline'
        ? 'Bridge offline.\n\nStart the omi bridge on your computer, then tap to retry.'
        : 'Microphone unavailable.\n\nTry Suggestions from the menu instead.'
    markBodyDirty()
    markStatusDirty()
    return
  }

  askPhase = 'listening'
  markBodyDirty()
  markStatusDirty()
}

/** Stop the microphone and let the bridge answer what it heard. */
async function stopAndAsk(reason: 'tap' | 'cap'): Promise<void> {
  if (!recorder.isListening()) return
  // Repainted before awaiting the SDK: turning the microphone off is a round
  // trip, and a screen still saying "Listening" after the user tapped reads as
  // a dropped input.
  askPhase = 'thinking'
  markBodyDirty()
  markStatusDirty()

  const asked = await recorder.stop(reason)
  if (asked) {
    startPending('chat')
  } else {
    askPhase = 'error'
    askHint = 'Bridge offline.\n\nThe question could not be sent. Tap to retry.'
    markBodyDirty()
    markStatusDirty()
  }
}

/** Throw the question away and go back to the menu. */
async function cancelListening(): Promise<void> {
  // `ask_stop` still goes out — it is the only thing that releases the buffer
  // the bridge opened — so the answer it produces has to be discarded.
  const asked = await recorder.stop('cancel')
  if (asked) staleAsks++
  askPhase = 'idle'
  askHint = ''
  console.log('[app] ask cancelled')
  await goHome()
}

/** Stop listening and show `reason` in the chat view. */
async function abortListening(reason: string): Promise<void> {
  const asked = await recorder.stop('cancel')
  if (asked) staleAsks++
  askPhase = 'error'
  askHint = reason
  markBodyDirty()
  markStatusDirty()
}

/** Ask the next canned question. No microphone involved. */
async function askSuggestion(advance: boolean): Promise<void> {
  const rebuild = view !== 'chat'
  if (advance) promptIndex = (promptIndex + 1) % PROMPTS.length
  view = 'chat'
  askMode = 'suggest'
  askPhase = 'answering'
  askHint = ''
  chatQuestion = PROMPTS[promptIndex % PROMPTS.length]
  chatAnswer = ''
  pageIndex = 0
  setPages('')
  if (rebuild) await renderCurrentView()
  else {
    markBodyDirty()
    markStatusDirty()
  }

  if (client.send({ type: 'chat', text: chatQuestion })) {
    console.log(`[app] asked: ${chatQuestion}`)
    startPending('chat')
  } else {
    askPhase = 'error'
    askHint = 'Bridge offline.\n\nStart the omi bridge on your computer, then tap to retry.'
    markBodyDirty()
    markStatusDirty()
  }
}

async function toggleCapture(): Promise<void> {
  const next = !captureOn
  captureOn = next
  if (await applyMic()) {
    console.log(`[app] capture=${captureOn ? 'on' : 'off'}`)
  } else {
    // Only keep the label flipped if the microphone actually flipped, so the
    // menu never claims to be capturing when it is not.
    captureOn = !next
    banner = 'Microphone unavailable'
    bannerAt = Date.now()
  }
  // List items cannot be updated in place, so the changed label needs a rebuild.
  await renderCurrentView()
}

async function goHome(): Promise<void> {
  clearPending()
  // Defensive: every caller stops the recorder first, but the microphone is
  // hardware and leaving it on is the worst bug this app can ship.
  if (recorder.isListening()) {
    const asked = await recorder.stop('cancel')
    if (asked) staleAsks++
  }
  view = 'home'
  askPhase = 'idle'
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
      await startListening()
      break
    case 'suggest':
      await askSuggestion(false)
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

  if (view === 'chat') {
    switch (gesture) {
      case 'up':
        movePage(-1)
        break
      case 'down':
        movePage(1)
        break
      case 'click':
        if (askMode === 'suggest') {
          // A tap moves to the next canned question, unless one is in flight.
          if (askPhase !== 'answering') await askSuggestion(true)
        } else if (askPhase === 'listening') {
          await stopAndAsk('tap')
        } else if (askPhase === 'idle' || askPhase === 'error') {
          await startListening()
        }
        // `starting`, `thinking` and `answering` are all "the glasses are busy
        // with the last question" — a tap there would race the reply.
        break
      case 'double':
        if (askPhase === 'listening' || askPhase === 'starting') await cancelListening()
        else await goHome()
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

// `audioControl` needs the start-up page to exist, so this is the earliest it
// can run. A WebView that died mid-question — a reload, a crash — may have left
// the microphone open with nothing reading it; boot from a known-off state.
try {
  await serialize('audioControl(reset)', () => bridge.audioControl(false))
  console.log('[app] microphone reset to off at start-up')
} catch (error) {
  console.warn('[app] could not reset the microphone at start-up:', error)
}

// A background restore can land before or after the start-up page exists. If
// it already moved us off the home view, rebuild into the right layout now.
if (view !== 'home') await renderCurrentView()

// Serialize gesture handling too: two overlapping handlers could interleave
// rebuilds and leave the display showing one view's body under another's list.
let inputChain: Promise<void> = Promise.resolve()

/** Run `task` behind everything already queued, so timer-driven work (the
 *  recording cap, a bridge drop) cannot interleave with a gesture. */
function enqueue(task: () => Promise<void>): void {
  inputChain = inputChain.then(task).catch((error) => console.error('[app] queued task failed:', error))
}

bridge.onEvenHubEvent((event) => {
  // Audio shares this listener with input. It arrives ~10 times a second, so
  // it is handled first and never logged per frame.
  const audio = event.audioEvent as { audioPcm?: unknown; audio_pcm?: unknown } | undefined
  if (audio) {
    recorder.feed(audio.audioPcm ?? audio.audio_pcm ?? audio)
    return
  }

  const decoded = decode(event)
  if (!decoded) return
  console.log(`[app] gesture=${decoded.gesture}${decoded.listIndex === undefined ? '' : ` index=${decoded.listIndex}`}`)
  enqueue(() => handleGesture(decoded.gesture, decoded.listIndex))
})

// The microphone is hardware: a reload or a closed WebView with a live capture
// leaves it running on the user's face until the glasses time it out.
const releaseMic = () => {
  recorder.teardown()
  if (micOn) {
    micOn = false
    void bridge.audioControl(false)
  }
}
window.addEventListener('beforeunload', releaseMic)
window.addEventListener('pagehide', releaseMic)

console.log('[app] ready')
