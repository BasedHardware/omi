---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_videoframe
title: VideoFrame Struct
scraped_at: 2026-07-03T14:24:14.767Z
---

# VideoFrame Struct
Extends
Sendable
Represents a single frame of video data from a Meta Wearables device. Contains the raw video sample buffer and provides utilities for converting to UIImage.
## Signature
```swift
struct VideoFrame: Sendable
```
## Properties
sampleBuffer
: CMSampleBuffer
[Get]
|
Provides access to the underlying video sample buffer.
**Important**: While this property exposes the raw `CoreMedia/CMSampleBuffer` for advanced use cases, callers must treat it as read-only. Mutating the sample buffer's attachments, timing information, or underlying pixel buffer may lead to undefined behavior, crashes, or data corruption since the buffer is shared across multiple contexts without synchronization.
For safe image conversion, use [makeUIImage()](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_videoframe#makeUIImage) instead.
|
## Functions
makeUIImage
()
|
Converts the video frame to a UIImage for display or processing. This method handles the conversion from the underlying CoreMedia sample buffer to a UIImage.
Signature
```swift
public func makeUIImage() -> sending UIImage?
```
Returns
`sending UIImage`
A UIImage representation of the video frame, or nil if conversion fails.
|
