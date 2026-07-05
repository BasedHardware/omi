---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesessionerror
title: DeviceSessionError Enum
scraped_at: 2026-07-03T14:24:20.251Z
---

# DeviceSessionError Enum
Extends
[DatError](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_daterror), Equatable
Errors that can occur during [DeviceSession](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesession) operations.
## Signature
```swift
enum DeviceSessionError: DatError, Equatable
```
## Enumeration Constants
Member | Description |
noEligibleDevice
|
No device is available (not connected, powered off, or incompatible).
|
sessionAlreadyStopped
|
An operation was attempted on a session that has already stopped.
|
sessionAlreadyExists
|
A non-stopped session already exists for this device.
|
sessionIdle
|
The operation was called on a session that is still idle (not yet started).
|
capabilityAlreadyActive
|
A capability of the same type is already attached to the session.
|
capabilityNotFound
|
No capability of the given type is attached to the session.
|
unexpectedError(String)
|
An unexpected error occurred.
|
thermalCritical
|
The device thermal state has reached a critical level.
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
datAppOnTheGlassesUpdateRequired
|
The app on the glasses needs an update before the session can start.
|
dwaUnavailable
|
The DAT Wearables App on the glasses is not reachable.
|
## Properties
description
: String
[Get]
|
A description of the error for debugging and logging.
|
errorDescription
: String?
[Get]
|
|
