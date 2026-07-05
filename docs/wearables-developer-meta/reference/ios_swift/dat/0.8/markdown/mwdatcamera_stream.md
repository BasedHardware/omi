---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_stream
title: Stream Class
scraped_at: 2026-07-03T14:24:13.716Z
---

# Stream Class
Extends
Sendable
Modifiers:
const A class for managing media streaming capabilities with Meta Wearables devices. Handles video streaming, photo capture, and provides real-time state updates.
In Swift, create a [Stream](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_stream) by first creating and starting a [DeviceSession](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesession), then calling `DeviceSession/addStream(config:)`. The returned stream is attached to that device session and stops automatically when the parent device session stops.
## Signature
```swift
class Stream: Sendable
```
## Properties
errorPublisher
: any Announcer<StreamError>
[Get]
|
Publisher for errors that occur during the streaming session.
|
photoDataPublisher
: any Announcer<PhotoData>
[Get]
|
Publisher for photo data captured during the streaming session.
|
state
: [StreamState](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_streamstate)
[Get]
|
The current state of the streaming session.
|
statePublisher
: any Announcer<StreamState>
[Get]
|
Publisher for streaming session state changes.
|
streamConfiguration
: [StreamConfiguration](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_streamconfiguration)
|
The configuration used for this streaming session.
|
videoFramePublisher
: any Announcer<VideoFrame>
[Get]
|
Publisher for video frames received from the streaming session.
|
## Functions
capturePhoto
(
format
)
|
Captures a still photo during streaming.
Triggers a photo capture while video streaming is active. The captured photo is delivered through [photoDataPublisher](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_stream#photoDataPublisher). Video streaming is temporarily paused during capture and automatically resumes after photo delivery.
Signature
```swift
public func capturePhoto( format: PhotoCaptureFormat) -> Bool
```
Parameters
`format: [PhotoCaptureFormat](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_photocaptureformat)`
The desired image format.
Returns
`Bool`   `true` if the capture request was accepted, `false` if no device session is active, no high-bandwidth link lease (BTC or WiFi) is held, a capture is already in progress, or the underlying capture request fails.
|
start
()
|
Starts video streaming from the device.
Begins streaming video frames from the currently available device. If no device is currently available, the session enters `.waitingForDevice` state and automatically connects when a device becomes available. Video frames are delivered through [videoFramePublisher](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_stream#videoFramePublisher).
State transitions: `.stopped` -> `.waitingForDevice` (no device) or `.stopped` -> `.starting` -> `.streaming` (with device).
The session monitors for device availability and automatically connects when a device becomes available and publishes errors if the device is invalid. The session automatically stops when an error occurs or when the device session ends externally (e.g., device powered off).
Errors published to [errorPublisher](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_stream#errorPublisher): - [StreamError.deviceNotFound(_:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_streamerror#deviceNotFound) - [StreamError.deviceNotConnected(_:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_streamerror#deviceNotConnected) - [StreamError.timeout](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_streamerror#timeout) - [StreamError.permissionDenied](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_streamerror#permissionDenied) - [StreamError.hingesClosed](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_streamerror#hingesClosed) - [StreamError.internalError](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_streamerror#internalError)
Signature
```swift
public func start()
```
|
stop
()
|
Stops video streaming and releases all resources.
Shuts down the streaming pipeline and transitions to `.stopped` state.
State transitions: Any state -> `.stopping` -> `.stopped`
Signature
```swift
public func stop()
```
|
