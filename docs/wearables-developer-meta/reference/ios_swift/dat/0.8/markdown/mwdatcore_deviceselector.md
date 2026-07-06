---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_deviceselector
title: DeviceSelector Protocol
scraped_at: 2026-07-03T14:24:18.960Z
---

# DeviceSelector Protocol
Extends
Sendable
Protocol for selecting which device should be used for operations. Device selectors determine which available device should receive commands or stream data.
## Signature
```swift
protocol DeviceSelector: Sendable
```
## Properties
activeDevice
: DeviceIdentifier?
[Get]
|
The currently active device identifier, if any.
|
## Functions
activeDeviceStream
()
|
Creates a stream of active device changes.
Signature
```swift
public func activeDeviceStream() -> AnyAsyncSequence
```
Returns
`AnyAsyncSequence `
|
