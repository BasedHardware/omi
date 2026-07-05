---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_sessionstate
title: SessionState Enum
scraped_at: 2026-07-03T14:24:23.683Z
---

# SessionState Enum
Extends
Int, Sendable
Represents the current state of a device session in the Wearables Device Access Toolkit.
## Signature
```swift
enum SessionState: Int, Sendable
```
## Enumeration Constants
Member | Description |
stopped
|
The session is not active and not attempting to connect.
|
waitingForDevice
|
The session is waiting for a device to become available for connection.
|
running
|
The session is actively running and processing data from the device.
|
paused
|
The session is temporarily paused but maintains its connection.
|
unknown
|
The session state is not currently determinable.
|
## Properties
description
: String
[Get]
|
Provides a human-readable description of the session state.
|
