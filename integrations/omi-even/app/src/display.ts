/** Serialized access to the glasses display.
 *
 *  Every SDK call goes through one FIFO queue. Two reasons:
 *   - concurrent bridge calls can crash the BLE connection, so exactly one is
 *     ever in flight;
 *   - a flaky hop leaves a call hanging for ~30s, so each one races a 5s
 *     timeout and the queue keeps moving instead of wedging.
 *
 *  A failed call is logged and dropped: the display is not the source of truth,
 *  the next render redraws whatever the state says.
 */
import {
  CreateStartUpPageContainer,
  ListContainerProperty,
  ListItemContainerProperty,
  RebuildPageContainer,
  StartUpPageCreateResult,
  TextContainerProperty,
  TextContainerUpgrade,
} from '@evenrealities/even_hub_sdk'
import type { EvenAppBridge } from '@evenrealities/even_hub_sdk'
import {
  BODY_HEIGHT,
  BODY_ID,
  BODY_NAME,
  BRIDGE_CALL_TIMEOUT_MS,
  CANVAS_HEIGHT,
  CANVAS_WIDTH,
  HOME_LIST_ID,
  HOME_LIST_NAME,
  STATUS_HEIGHT,
  STATUS_ID,
  STATUS_NAME,
} from './config.ts'

/** Tail of the call chain. Every queued call links onto this. */
let chain: Promise<unknown> = Promise.resolve()

function withTimeout<T>(label: string, task: () => Promise<T>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`${label} timed out after ${BRIDGE_CALL_TIMEOUT_MS}ms`)), BRIDGE_CALL_TIMEOUT_MS)
    task().then(
      (value) => {
        clearTimeout(timer)
        resolve(value)
      },
      (error) => {
        clearTimeout(timer)
        reject(error)
      },
    )
  })
}

/** Queue one bridge call behind every call already in flight. */
export function serialize<T>(label: string, task: () => Promise<T>): Promise<T> {
  const run = chain.then(() => withTimeout(label, task))
  // Swallow on the *chain* only — the returned promise still rejects, so
  // callers can react, but one failure never poisons later calls.
  chain = run.catch(() => undefined)
  return run
}

// ------------------------------------------------------------------ builders

/** Bottom strip: connection state, page position, or the latest push banner. */
function statusContainer(content: string): TextContainerProperty {
  return new TextContainerProperty({
    xPosition: 0,
    yPosition: BODY_HEIGHT,
    width: CANVAS_WIDTH,
    height: STATUS_HEIGHT,
    borderWidth: 0,
    borderColor: 5,
    paddingLength: 4,
    containerID: STATUS_ID,
    containerName: STATUS_NAME,
    content,
    isEventCapture: 0,
  })
}

/** Home menu. The OS list owns the highlight; `isItemSelectBorderEn` draws it. */
function homeListContainer(items: string[]): ListContainerProperty {
  return new ListContainerProperty({
    xPosition: 0,
    yPosition: 0,
    width: CANVAS_WIDTH,
    height: BODY_HEIGHT,
    borderWidth: 0,
    borderColor: 5,
    paddingLength: 4,
    containerID: HOME_LIST_ID,
    containerName: HOME_LIST_NAME,
    // Exactly one container per page may capture events, and on the home page
    // that has to be the list so scroll moves the selection.
    isEventCapture: 1,
    itemContainer: new ListItemContainerProperty({
      itemCount: items.length,
      itemWidth: CANVAS_WIDTH,
      isItemSelectBorderEn: 1,
      itemName: items,
    }),
  })
}

/** Body of a read/chat view: one big text box that owns the touch events. */
function bodyContainer(content: string): TextContainerProperty {
  return new TextContainerProperty({
    xPosition: 0,
    yPosition: 0,
    width: CANVAS_WIDTH,
    height: BODY_HEIGHT,
    borderWidth: 0,
    borderColor: 5,
    paddingLength: 4,
    containerID: BODY_ID,
    containerName: BODY_NAME,
    content,
    isEventCapture: 1,
  })
}

// ------------------------------------------------------------------- surface

export class Display {
  /** Which layout is currently on the glasses, so `setBody` knows whether the
   *  body container exists or a rebuild is needed first. */
  private layout: 'none' | 'home' | 'detail' = 'none'
  private readonly bridge: EvenAppBridge

  constructor(bridge: EvenAppBridge) {
    this.bridge = bridge
  }

  currentLayout(): 'none' | 'home' | 'detail' {
    return this.layout
  }

  /**
   * The one and only `createStartUpPageContainer` call. Called exactly once at
   * boot with the home layout; every later screen goes through
   * `rebuildPageContainer`.
   */
  async createStartUpPage(items: string[], status: string): Promise<void> {
    const result = await serialize('createStartUpPageContainer', () =>
      this.bridge.createStartUpPageContainer(
        new CreateStartUpPageContainer({
          containerTotalNum: 2,
          listObject: [homeListContainer(items)],
          textObject: [statusContainer(status)],
        }),
      ),
    )
    this.layout = 'home'
    if (result === StartUpPageCreateResult.success) {
      console.log('[app] page ready: created')
    } else if (result === StartUpPageCreateResult.invalid) {
      // The host rejects a second create for a page that already exists, which
      // is exactly what a WebView reload looks like. The containers are still
      // there and updates still land on them, so this is not a failure — but
      // `oversize` and `outOfMemory` below genuinely are.
      console.warn('[app] page ready: reused the containers from before the reload')
    } else {
      console.error('[app] createStartUpPageContainer failed:', result)
    }
  }

  /** Swap to the home layout. Flickers — list contents cannot update in place. */
  async showHome(items: string[], status: string): Promise<void> {
    await serialize('rebuildPageContainer(home)', () =>
      this.bridge.rebuildPageContainer(
        new RebuildPageContainer({
          containerTotalNum: 2,
          listObject: [homeListContainer(items)],
          textObject: [statusContainer(status)],
        }),
      ),
    )
    this.layout = 'home'
    console.log('[app] layout=home')
  }

  /** Swap to the text layout. Flickers once; later text goes through `setBody`. */
  async showDetail(body: string, status: string): Promise<void> {
    await serialize('rebuildPageContainer(detail)', () =>
      this.bridge.rebuildPageContainer(
        new RebuildPageContainer({
          containerTotalNum: 2,
          textObject: [bodyContainer(body), statusContainer(status)],
        }),
      ),
    )
    this.layout = 'detail'
    console.log('[app] layout=detail')
  }

  /**
   * Flicker-free in-place body update — the path streaming chat answers use.
   * Returns false without doing anything unless the detail layout is on screen,
   * because the container ID and name must both exist or the host drops the
   * update without reporting an error.
   */
  async setBody(content: string): Promise<boolean> {
    if (this.layout !== 'detail') return false
    await serialize('textContainerUpgrade(body)', () =>
      this.bridge.textContainerUpgrade(
        new TextContainerUpgrade({ containerID: BODY_ID, containerName: BODY_NAME, content }),
      ),
    )
    return true
  }

  /** In-place status strip update. Present on every layout. */
  async setStatus(content: string): Promise<void> {
    if (this.layout === 'none') return
    await serialize('textContainerUpgrade(status)', () =>
      this.bridge.textContainerUpgrade(
        new TextContainerUpgrade({ containerID: STATUS_ID, containerName: STATUS_NAME, content }),
      ),
    )
  }

  /** Raise the system exit dialog and let the user confirm. */
  async requestExit(): Promise<void> {
    await serialize('shutDownPageContainer', () => this.bridge.shutDownPageContainer(1))
  }
}

export { CANVAS_HEIGHT, CANVAS_WIDTH }
