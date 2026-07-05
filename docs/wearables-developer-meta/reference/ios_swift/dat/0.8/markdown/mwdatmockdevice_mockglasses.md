---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatmockdevice_mockglasses
title: MockGlasses Protocol
scraped_at: 2026-07-03T14:24:35.778Z
---

# MockGlasses Protocol
Extends
[MockDevice](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatmockdevice_mockdevice)
Protocol for simulating smart glasses behavior in testing and development. Provides functionality for simulating folding/unfolding actions and camera capabilities.
## Signature
```swift
protocol MockGlasses: MockDevice
```
## Properties
services
: [MockGlassesServices](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatmockdevice_mockglassesservices)
[Get]
|
Container for services available on this device.
|
## Functions
fold
()
|
Simulates folding the glasses into a closed position.
Signature
```swift
public func fold()
```
|
unfold
()
|
Simulates unfolding the glasses into an open position.
Signature
```swift
public func unfold()
```
|
