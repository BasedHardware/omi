---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_videoerror
title: VideoError Enum
scraped_at: 2026-07-03T14:24:32.339Z
---

# VideoError Enum
Extends
[DatError](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_daterror), Equatable
Errors that occur during video playback via [VideoPlayer](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_videoplayer).
These are routed to [VideoPlayer.onError](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_videoplayer#onError) when set.
## Signature
```swift
enum VideoError: DatError, Equatable
```
## Enumeration Constants
Member | Description |
streamRejected
|
The glasses rejected the video stream or did not acknowledge readiness in time.
|
playbackFailed(VideoErrorType)
|
The glasses reported a playback error with the given `VideoErrorType`.
|
## Properties
description
: String
[Get]
|
|
