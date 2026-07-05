---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatmockdevice_mockdevicekitinterface
title: MockDeviceKitInterface Protocol
scraped_at: 2026-07-03T14:24:35.738Z
---

# MockDeviceKitInterface Protocol
Extends
Sendable
Interface for managing mock Meta Wearables devices for testing and development.
## Signature
```swift
protocol MockDeviceKitInterface: Sendable
```
## Properties
isEnabled
: Bool
[Get]
|
Whether MockDeviceKit is currently enabled.
|
pairedDevices
: [MockDevice]
[Get]
|
The list of all currently paired mock devices.
|
permissions
: [MockPermissions](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatmockdevice_mockpermissions)
[Get]
|
Interface for configuring mock permission behavior.
|
## Functions
disable
()
|
Disables MockDeviceKit, restoring real providers and unpairing all mock devices.
Signature
```swift
public func disable()
```
|
enable
(
config
)
|
Enables MockDeviceKit, injecting fake providers into the registration and device layers.
Safe to call regardless of whether `Wearables.configure()` has been called — MockDeviceKit will auto-configure Wearables if needed.
Signature
```swift
public func enable( config: MockDeviceKitConfig)
```
Parameters
`config: [MockDeviceKitConfig](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatmockdevice_mockdevicekitconfig)`
Configuration options for MockDeviceKit behavior.
|
pairGlasses
(
model
)
|
Pairs a simulated glasses device of the specified model.
Signature
```swift
public func pairGlasses( model: GlassesModel) -> MockGlasses
```
Parameters
`model: [GlassesModel](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatmockdevice_glassesmodel)`
The glasses model to simulate.
Returns
`[MockGlasses](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatmockdevice_mockglasses)`
A mock glasses instance.
Throws
|
startTestServer
(
portFilePath
)
|
Starts a local test server for mock device communication.
Signature
```swift
public func startTestServer( portFilePath: String?) -> UInt16
```
Parameters
`portFilePath: String?`
Optional path to a file where the server port will be written.
Returns
`UInt16`
The port number the server is listening on.
|
stopTestServer
()
|
Stops the running test server.
Signature
```swift
public func stopTestServer()
```
|
unpairDevice
(
device
)
|
Unpairs a simulated device.
Signature
```swift
public func unpairDevice(_ device: MockDevice)
```
Parameters
`_ device: [MockDevice](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatmockdevice_mockdevice)`
The mock device to unpair.
|
