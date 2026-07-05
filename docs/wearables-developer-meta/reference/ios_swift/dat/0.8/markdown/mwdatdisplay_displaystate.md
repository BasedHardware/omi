---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_displaystate
title: DisplayState Enum
scraped_at: 2026-07-03T14:24:28.526Z
---

# DisplayState Enum
The current lifecycle state of a [Display](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_display).
State transitions:
```swift
stopped → starting → started → stopping → stopped
```
## Signature
```swift
enum DisplayState
```
## Enumeration Constants
Member | Description |
starting
|
The display is in the process of starting up.
|
started
|
The display has started and is ready to receive content via [Display.send(_:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_display#send).
|
stopping
|
The display is in the process of stopping.
|
stopped
|
The display is stopped, either because it hasn't been started or the device disconnected.
|
