---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicetype
title: DeviceType Extension
scraped_at: 2026-07-03T14:24:20.713Z
---

# DeviceType Extension
Extends
String, CaseIterable, Sendable
Represents the types of Meta Wearables devices supported by the Wearables Device Access Toolkit.
Each device type corresponds to a specific Meta Wearables hardware variant with distinct capabilities and features.
## Signature
```swift
enum DeviceType: String, CaseIterable, Sendable
```
## Enumeration Constants
Member | Description |
unknown
|
Unknown or invalid device type
|
rayBanMeta
|
Ray-Ban Meta
|
oakleyMetaHSTN
|
Oakley Meta HSTN
|
oakleyMetaVanguard
|
Oakley Meta Vanguard
|
metaRayBanDisplay
|
Meta Ray-Ban Display
|
rayBanMetaOptics
|
Ray-Ban Meta Optics
|
metaGlasses
|
Meta Glasses
|
## Properties
supportsDisplay
: Bool
[Get]
|
Returns whether this device type has a built-in display.
|
