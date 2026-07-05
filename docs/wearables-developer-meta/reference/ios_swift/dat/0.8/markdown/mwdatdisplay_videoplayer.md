---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_videoplayer
title: VideoPlayer Struct
scraped_at: 2026-07-03T14:24:32.485Z
---

# VideoPlayer Struct
Extends
[DisplayableView](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_displayableview), Sendable
A video player configuration to be sent to the glasses via [Display.send(_:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_display#send).
Use `Provider/uri(_:)` for URL-based playback.
## Signature
```swift
struct VideoPlayer: DisplayableView, Sendable
```
## Constructors
init
(
provider
, codec
, onError
)
|
Creates a video player with the given provider and parameters.
Signature
```swift
public init( provider: Provider, codec: VideoCodec, onError: (@Sendable (VideoError) -> Void)?)
```
Parameters
`provider: Provider`
The video data source (URL or stream).
`codec: [VideoCodec](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_videocodec)`
The video codec. Defaults to `.mp4`.
`onError: (@Sendable ([VideoError](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_videoerror)) -> Void)`
Optional error handler for video-specific errors. Defaults to `nil`.
|
## Properties
codec
: VideoCodec
|
The video codec. Defaults to `.mp4`.
|
onError
: (@Sendable (VideoError) -> Void)?
|
Called when a video stream error occurs (e.g. stream rejection by the glasses).
Device disconnection errors are thrown as [DisplayError.deviceDisconnected](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_displayerror#deviceDisconnected) from [Display.send(_:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_display#send) regardless of this handler.
|
provider
: Provider
|
The video data source.
|
