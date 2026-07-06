---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_streamerror
title: StreamError Enum
scraped_at: 2026-07-03T14:24:15.152Z
---

# StreamError Enum
Extends
[DatError](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_daterror), Equatable
Errors that can occur during streaming sessions.
## Signature
```swift
enum StreamError: DatError, Equatable
```
## Enumeration Constants
Member | Description |
internalError
|
An internal error occurred.
|
deviceNotFound([DeviceIdentifier](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_deviceidentifier))
|
The specified device could not be found.
|
deviceNotConnected([DeviceIdentifier](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_deviceidentifier))
|
The specified device is not connected.
|
timeout
|
The operation timed out.
|
videoStreamingError
|
Video streaming encountered an error.
|
permissionDenied
|
Camera permission was denied.
|
hingesClosed
|
The device hinges were closed during streaming.
|
thermalCritical
|
The device thermal state has reached a critical level that may affect streaming performance.
|
thermalEmergency
|
The device thermal state has reached an emergency level and the device is shutting down.
|
peakPowerShutdown
|
The device has entered peak power shutdown.
|
batteryCritical
|
The device battery has reached a critically low level.
|
## Properties
description
: String
[Get]
|
A description of the error
|
errorDescription
: String?
[Get]
|
|
