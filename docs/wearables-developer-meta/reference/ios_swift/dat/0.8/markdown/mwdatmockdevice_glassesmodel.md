---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatmockdevice_glassesmodel
title: GlassesModel Enum
scraped_at: 2026-07-03T14:24:33.110Z
---

# GlassesModel Enum
Extends
String, CaseIterable, Sendable
Identifies a glasses model for use with [MockDeviceKitInterface.pairGlasses(model:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatmockdevice_mockdevicekitinterface#pairGlasses).
Each case represents a supported displayless glasses model that MockDeviceKit can simulate. Display-capable devices and non-glasses form factors will use separate types when supported.
## Signature
```swift
enum GlassesModel: String, CaseIterable, Sendable
```
## Enumeration Constants
Member | Description |
rayBanMeta
|
Ray-Ban Meta smart glasses.
|
oakleyMetaHSTN
|
Oakley Meta HSTN smart glasses.
|
oakleyMetaVanguard
|
Oakley Meta Vanguard smart glasses.
|
rayBanMetaOptics
|
Ray-Ban Meta Optics smart glasses.
|
metaGlasses
|
Meta Glasses smart glasses.
|
