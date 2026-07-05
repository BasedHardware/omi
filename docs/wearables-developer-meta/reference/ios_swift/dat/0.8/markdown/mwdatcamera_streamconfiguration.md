---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_streamconfiguration
title: StreamConfiguration Struct
scraped_at: 2026-07-03T14:24:13.226Z
---

# StreamConfiguration Struct
Extends
Sendable
Configuration for a media streaming session with a Meta Wearables device. Defines video codec, resolution, frame delivery strategy, and target frame rate.
## Signature
```swift
struct StreamConfiguration: Sendable
```
## Constructors
init
(
videoCodec
, resolution
, frameRate
)
|
Creates a new stream session configuration with specified parameters.
Signature
```swift
public init( videoCodec: VideoCodec, resolution: StreamingResolution, frameRate: UInt)
```
Parameters
`videoCodec: [VideoCodec](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_videocodec)`
The video codec to use for streaming.
`resolution: [StreamingResolution](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_streamingresolution)`
The resolution for video streaming.
`frameRate: UInt`
The target frame rate for streaming.
|
init
()
|
Creates a new stream session configuration with default settings. Uses raw video codec, medium resolution, deliver-all frame strategy, and 30 FPS.
Signature
```swift
public init()
```
|
## Properties
frameRate
: UInt
|
The target frame rate for the streaming session.
|
resolution
: [StreamingResolution](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_streamingresolution)
|
The resolution at which to stream video content.
|
videoCodec
: [VideoCodec](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_videocodec)
|
The video codec to use for streaming.
|
