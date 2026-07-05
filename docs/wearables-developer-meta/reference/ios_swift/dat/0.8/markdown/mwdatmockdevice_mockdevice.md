---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatmockdevice_mockdevice
title: MockDevice Protocol
scraped_at: 2026-07-03T14:24:34.036Z
---

# MockDevice Protocol
Extends
Sendable
## Signature
```swift
protocol MockDevice: Sendable
```
## Properties
deviceIdentifier
: DeviceIdentifier
[Get]
|
The unique device identifier for this mock device.
|
## Functions
doff
()
|
Simulates taking off (doffing) the device.
Signature
```swift
public func doff()
```
|
don
()
|
Simulates putting on (donning) the device.
Signature
```swift
public func don()
```
|
powerOff
()
|
Powers off the mock device.
Signature
```swift
public func powerOff()
```
|
powerOn
()
|
Powers on the mock device.
Signature
```swift
public func powerOn()
```
|
