---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_display
title: Display Class
scraped_at: 2026-07-03T14:24:26.975Z
---

# Display Class
Extends
Sendable
Modifiers:
const Manages rendering content on a Meta Wearables display.
A `Display` handles the connection to the glasses' display service and provides methods to send views and video to the screen. Create one via `DeviceSession/addDisplay()`, which targets the parent session's device.
## Signature
```swift
class Display: Sendable
```
## Properties
onPlaybackEvent
: (@Sendable (VideoPlaybackEvent) -> Void)?
[Get][Set]
|
Called when a video playback event is received from the glasses.
|
state
: [DisplayState](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_displaystate)
[Get]
|
The current session state.
|
statePublisher
: any Announcer<DisplayState>
[Get]
|
Publishes state changes for this display.
|
## Functions
clearDisplay
()
|
Clears content currently rendered on the wearable display.
This removes the current display content without stopping the display capability or detaching it from the parent session. After a successful clear, the same [Display](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_display) can render new content by calling [send(_:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_display#send).
The clear operation uses the same acknowledgement and error path as normal display content.
Signature
```swift
public func clearDisplay()
```
Throws
|
send
(
view
)
|
Sends a displayable view or video to the connected device.
Signature
```swift
public func send(_ view: some DisplayableView)
```
Parameters
`_ view: some [DisplayableView](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_displayableview)`
The view or [VideoPlayer](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_videoplayer) to display on the glasses.
Throws
|
sendVideoStop
()
|
Stops any active video playback on the glasses.
Call this after all video data has been sent but the glasses are still playing, to end playback early and free display resources.
Signature
```swift
public func sendVideoStop()
```
|
start
()
|
Starts the display capability, connecting to the device's display service.
Monitors for device availability and automatically connects when a device becomes available. Observe [statePublisher](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_display#statePublisher) for the transition to [DisplayState.started](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_displaystate#started), which indicates the display is ready to receive content via [send(_:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_display#send).
Signature
```swift
public func start()
```
|
stop
()
|
Requests to stop the display session and release all resources. Observe [statePublisher](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_display#statePublisher) for the transition to [DisplayState.stopped](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_displaystate#stopped).
Closes the display channel and transitions to [DisplayState.stopped](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_displaystate#stopped). After stopping, the display detaches itself from its [DeviceSession](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesession); call `DeviceSession/addDisplay()` for a new instance to display again.
Signature
```swift
public func stop()
```
|
