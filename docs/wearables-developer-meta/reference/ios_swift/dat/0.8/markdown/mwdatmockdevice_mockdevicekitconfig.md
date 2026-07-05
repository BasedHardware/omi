---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatmockdevice_mockdevicekitconfig
title: MockDeviceKitConfig Struct
scraped_at: 2026-07-03T14:24:35.368Z
---

# MockDeviceKitConfig Struct
Extends
Sendable
Configuration options for MockDeviceKit.
## Signature
```swift
struct MockDeviceKitConfig: Sendable
```
## Constructors
init
(
initiallyRegistered
, initialPermissionsGranted
)
|
Signature
```swift
public init( initiallyRegistered: Bool, initialPermissionsGranted: Bool)
```
Parameters
`initiallyRegistered: Bool`
`initialPermissionsGranted: Bool`
|
## Properties
initiallyRegistered
: Bool
|
Whether the mock device should start in a registered state. When `true` (default), `enable()` immediately transitions to `.registered`. When `false`, the state starts as `.unavailable`, allowing `startRegistration()` to be tested.
|
initialPermissionsGranted
: Bool
|
Whether permissions should start as granted. When `true` (default), all permissions are granted after `enable()`. When `false`, all permissions start denied — tests must explicitly grant via `set(_ permission:, .granted)`. Forced to `false` when `initiallyRegistered` is `false` (can't have permissions without registration).
|
