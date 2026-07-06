---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesessionstate
title: DeviceSessionState Enum
scraped_at: 2026-07-03T14:24:20.305Z
---

# DeviceSessionState Enum
Extends
Equatable, Sendable
Represents the current state of a [DeviceSession](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesession).
## Signature
```swift
enum DeviceSessionState: Equatable, Sendable
```
## Enumeration Constants
Member | Description |
idle
|
The session has been created but [DeviceSession.start()](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesession#start) has not been called yet.
|
starting
|
The session is connecting to the device.
|
started
|
The session is connected and active.
|
paused
|
The session is temporarily paused (device-initiated, e.g. cap-touch).
|
stopping
|
The session is stopping and cleaning up resources.
|
stopped
|
The session has ended. A new session must be created via [WearablesInterface.createSession(deviceSelector:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_wearablesinterface#createSession).
|
## Properties
description
: String
[Get]
|
Provides a human-readable description of the session state.
|
