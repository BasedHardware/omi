---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_specificdeviceselector
title: SpecificDeviceSelector Class
scraped_at: 2026-07-03T14:24:24.796Z
---

# SpecificDeviceSelector Class
Extends
[DeviceSelector](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_deviceselector)
Modifiers:
const A device selector that always selects a specific, predetermined device. Use this when you want to target operations to a particular device by its identifier.
## Signature
```swift
class SpecificDeviceSelector: DeviceSelector
```
## Constructors
init
(
device
)
|
Creates a device selector that targets a specific device.
Signature
```swift
public init( device: DeviceIdentifier)
```
Parameters
`device: [DeviceIdentifier](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_deviceidentifier)`
The identifier of the device to always select.
|
## Properties
activeDevice
: DeviceIdentifier?
[Get]
|
The currently active device identifier.
|
## Functions
activeDeviceStream
()
|
Creates a stream that immediately yields the specific device and then completes.
Signature
```swift
public func activeDeviceStream() -> AnyAsyncSequence
```
Returns
`AnyAsyncSequence `
|
