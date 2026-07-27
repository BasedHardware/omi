import {
  waitForEvenAppBridge,
  TextContainerProperty,
  TextContainerUpgrade,
  CreateStartUpPageContainer,
  OsEventTypeList,
  StartUpPageCreateResult,
} from '@evenrealities/even_hub_sdk'

/** Single source of truth for the display copy, so the initial render and every
 *  update stay in sync. 576x288 is the full G2 canvas. */
const screen = (count: number) => `Hello from G2!\n\nTap to count: ${count}\nDouble-tap to exit`

const CONTAINER_ID = 1

const bridge = await waitForEvenAppBridge()
console.log('[app] bridge ready')

const mainText = new TextContainerProperty({
  xPosition: 0,
  yPosition: 0,
  width: 576,
  height: 288,
  borderWidth: 0,
  borderColor: 5,
  paddingLength: 4,
  containerID: CONTAINER_ID,
  containerName: 'main',
  content: screen(0),
  isEventCapture: 1,
})

const result = await bridge.createStartUpPageContainer(
  new CreateStartUpPageContainer({
    containerTotalNum: 1,
    textObject: [mainText],
  }),
)

if (result !== StartUpPageCreateResult.success) {
  console.error('[app] createStartUpPageContainer failed:', result)
} else {
  console.log('[app] page created: success')
}

let count = 0

bridge.onEvenHubEvent((event) => {
  // Touch input arrives on one of two channels depending on the host. The
  // simulator reports tap / double-tap as a sysEvent and only scroll as a
  // textEvent; a capturing text container reports through textEvent. Read
  // whichever channel this event carries so one build works in both places.
  let eventType: OsEventTypeList | undefined
  if (event.textEvent) {
    if (event.textEvent.containerID !== CONTAINER_ID) return
    eventType = event.textEvent.eventType
  } else if (event.sysEvent) {
    eventType = event.sysEvent.eventType
  } else {
    return
  }

  switch (eventType) {
    // The host omits eventType for a plain tap, so an undefined type is
    // treated as a click rather than being dropped.
    case OsEventTypeList.CLICK_EVENT:
    case undefined:
      count += 1
      console.log(`[app] count=${count}`)
      bridge.textContainerUpgrade(
        new TextContainerUpgrade({
          containerID: CONTAINER_ID,
          containerName: 'main',
          content: screen(count),
        }),
      )
      break

    case OsEventTypeList.DOUBLE_CLICK_EVENT:
      console.log('[app] exit requested')
      // exitMode 1 = raise the system exit dialog and let the user confirm.
      bridge.shutDownPageContainer(1)
      break
  }
})
