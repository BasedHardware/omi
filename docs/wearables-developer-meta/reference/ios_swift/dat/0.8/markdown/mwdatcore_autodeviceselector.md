---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_autodeviceselector
title: AutoDeviceSelector Class
scraped_at: 2026-07-03T14:24:16.980Z
---

# AutoDeviceSelector Class
Extends
[DeviceSelector](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_deviceselector)
Modifiers:
const A device selector that automatically selects the best available device. Selects the first connected device from the devices list, falling back to the first device if none are connected.
## Signature
```swift
class AutoDeviceSelector: DeviceSelector
```
## Constructors
init
(
wearables
, filter
)
|
Creates an auto device selector that monitors the given wearables interface for device changes.
Signature
```swift
public init( wearables: WearablesInterface, filter: DeviceFilter?)
```
Parameters
`wearables: [WearablesInterface](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_wearablesinterface)`
The wearables interface to monitor for available devices.
`filter: [DeviceFilter?](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicefilter)`
An optional closure to apply additional filtering beyond connected and compatible. Return `true` to include a device, `false` to exclude it.
|
## Properties
activeDevice
: DeviceIdentifier?
[Get][Set]
|
The currently active device identifier.
|
## Functions
activeDeviceStream
()
|
Creates a stream of active device changes that updates whenever the device list changes.
Signature
```swift
public func activeDeviceStream() -> AnyAsyncSequence
```
Returns
`AnyAsyncSequence `
|
