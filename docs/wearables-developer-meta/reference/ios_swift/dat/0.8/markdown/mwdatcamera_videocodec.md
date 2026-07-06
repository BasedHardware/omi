---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_videocodec
title: VideoCodec Enum
scraped_at: 2026-07-03T14:24:14.940Z
---

# VideoCodec Enum
Extends
Sendable
Specifies the video codec to use for streaming.
## Signature
```swift
enum VideoCodec: Sendable
```
## Enumeration Constants
Member | Description |
raw
|
Raw decompressed video frames (420v YUV pixel buffers). - Note: Video frames are only delivered while the app is in the foreground. When the app enters background, frame delivery stops. Use [hvc1](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_videocodec#hvc1) if you need to receive frames while backgrounded.
|
hvc1
|
Compressed HEVC video frames (hvc1). Frames are delivered as compressed `CMSampleBuffer`s without decoding, in both foreground and background.
|
