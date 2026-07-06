---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatmockdevice_mockcamerakit
title: MockCameraKit Protocol
scraped_at: 2026-07-03T14:24:33.752Z
---

# MockCameraKit Protocol
Extends
Sendable
A suite for mocking camera functionality.
## Signature
```swift
protocol MockCameraKit: Sendable
```
## Functions
setCameraFeed
(
fileURL
)
|
Sets the camera feed from a video file.
Supported codecs: h.265
Mutually exclusive with [setCameraFeed(cameraFacing:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatmockdevice_mockcamerakit#setCameraFeed). Calling this clears any active camera source.
Signature
```swift
public func setCameraFeed( fileURL: URL)
```
Parameters
`fileURL: URL`
URL of the file containing the video stream.
|
setCameraFeed
(
cameraFacing
)
|
Sets the camera feed to stream live from the phone's camera.
Mutually exclusive with [setCameraFeed(fileURL:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatmockdevice_mockcamerakit#setCameraFeed). Calling this clears any active camera feed file.
Signature
```swift
public func setCameraFeed( cameraFacing: CameraFacing)
```
Parameters
`cameraFacing: [CameraFacing](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatmockdevice_camerafacing)`
Which phone camera to use.
|
setCapturedImage
(
fileURL
)
|
Sets the captured image from an image file.
Signature
```swift
public func setCapturedImage( fileURL: URL)
```
Parameters
`fileURL: URL`
URL of the file containing the image.
|
