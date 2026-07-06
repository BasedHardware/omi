---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_linkstate
title: LinkState Enum
scraped_at: 2026-07-03T14:24:21.168Z
---

# LinkState Enum
Extends
Equatable, Sendable
Represents the connection state between a device and the Wearables Device Access Toolkit.
## Signature
```swift
enum LinkState: Equatable, Sendable
```
## Enumeration Constants
Member | Description |
disconnected
|
The device is not connected to the Wearables Device Access Toolkit.
|
connecting
|
The device is currently attempting to establish a connection with the Wearables Device Access Toolkit.
|
connected
|
The device is successfully connected and ready for communication.
|
