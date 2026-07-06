---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicestate
title: DeviceState Struct
scraped_at: 2026-07-03T14:24:19.544Z
---

# DeviceState Struct
Extends
Sendable, Equatable
Represents the current state of a connected device.
Contains observable device state metrics such as the device's thermal level. Use [WearablesInterface.deviceStateStream(for:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_wearablesinterface#deviceStateStream) to observe changes.
## Signature
```swift
struct DeviceState: Sendable, Equatable
```
## Constructors
init
(
thermalLevel
)
|
Creates a new device state.
Signature
```swift
public init( thermalLevel: ThermalLevel)
```
Parameters
`thermalLevel: [ThermalLevel](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_thermallevel)`
The thermal level of the device. Defaults to [ThermalLevel.unknown](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_thermallevel#unknown).
|
## Properties
thermalLevel
: [ThermalLevel](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_thermallevel)
|
The current thermal level of the device.
|
