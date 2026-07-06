---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_displayerror
title: DisplayError Enum
scraped_at: 2026-07-03T14:24:28.778Z
---

# DisplayError Enum
Extends
[DatError](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_daterror), Equatable
Errors that can occur during display operations such as [Display.send(_:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_display#send) and [Display.clearDisplay()](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_display#clearDisplay).
## Signature
```swift
enum DisplayError: DatError, Equatable
```
## Enumeration Constants
Member | Description |
deviceNotFound
|
The specified device could not be found.
|
connectionNotAvailable
|
Device connection not available.
|
deviceDisconnected
|
Device is not connected or became disconnected during operation.
|
streamRejected
|
The glasses rejected the video stream or did not acknowledge readiness in time.
|
invalidVideoURL
|
The video URL is invalid (blank or unsupported scheme). Supported schemes are `http` and `https`.
|
displayError(String)
|
A display error was reported by the glasses (e.g., capability not active).
|
## Properties
description
: String
[Get]
|
|
