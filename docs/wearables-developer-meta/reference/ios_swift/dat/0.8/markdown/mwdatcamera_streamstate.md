---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_streamstate
title: StreamState Enum
scraped_at: 2026-07-03T14:24:14.580Z
---

# StreamState Enum
Extends
Sendable
Represents the current state of a media streaming session with a Meta Wearables device.
## Signature
```swift
enum StreamState: Sendable
```
## Enumeration Constants
Member | Description |
stopping
|
The session is in the process of stopping.
|
stopped
|
The session is completely stopped and not attempting to connect.
|
waitingForDevice
|
The session is waiting for a compatible device to become available.
|
starting
|
The session is in the process of starting up.
|
streaming
|
The session is actively streaming media data.
|
paused
|
The session is temporarily paused but maintains its connection.
|
