---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatmockdevicetestclient_mockdevicetestclient
title: MockDeviceTestClient Class
scraped_at: 2026-07-03T14:24:37.695Z
---

# MockDeviceTestClient Class
Extends
Sendable
Modifiers:
const Client for communicating with the MockDeviceKit test server from XCUITest processes.
Sends HTTP requests to the in-app `MockDeviceTestServer` to control mock devices during UI tests. The client reads the server port from a temp file written by the server.
## Signature
```swift
class MockDeviceTestClient: Sendable
```
## Constructors
init
(
port
)
|
Creates a client connecting to a specific port.
Signature
```swift
public init( port: UInt16)
```
Parameters
`port: UInt16`
The port the test server is listening on.
|
init
()
|
Creates a client that reads the server port from the default temp file. The server writes its port to `NSTemporaryDirectory() + "mwdat_test_server_port.txt"`.
Signature
```swift
public init()
```
|
init
(
portFilePath
)
|
Creates a client that reads the server port from the specified file path.
Signature
```swift
public init( portFilePath: String)
```
Parameters
`portFilePath: String`
Absolute path to the file containing the server port.
|
## Functions
captouchTap
(
deviceId
)
|
Simulates a single tap gesture on the device's capacitive touch sensor. Toggles the active session between paused and running states.
Signature
```swift
public func captouchTap( deviceId: String) -> Bool
```
Parameters
`deviceId: String`
The identifier of the device.
Returns
`Bool`   `true` if the command succeeded.
|
captouchTapAndHold
(
deviceId
)
|
Simulates a tap-and-hold gesture on the device's capacitive touch sensor. Stops the active session.
Signature
```swift
public func captouchTapAndHold( deviceId: String) -> Bool
```
Parameters
`deviceId: String`
The identifier of the device.
Returns
`Bool`   `true` if the command succeeded.
|
doff
(
deviceId
)
|
Simulates doffing (taking off) a mock device.
Signature
```swift
public func doff( deviceId: String) -> Bool
```
Parameters
`deviceId: String`
The identifier of the device to doff.
Returns
`Bool`   `true` if the command succeeded.
|
don
(
deviceId
)
|
Simulates donning (putting on) a mock device.
Signature
```swift
public func don( deviceId: String) -> Bool
```
Parameters
`deviceId: String`
The identifier of the device to don.
Returns
`Bool`   `true` if the command succeeded.
|
fold
(
deviceId
)
|
Simulates folding mock glasses.
Signature
```swift
public func fold( deviceId: String) -> Bool
```
Parameters
`deviceId: String`
The identifier of the glasses to fold.
Returns
`Bool`   `true` if the command succeeded.
|
getDeviceState
()
|
Returns the current device state from the server.
Signature
```swift
public func getDeviceState() -> [String: Any]?
```
Returns
`[String: Any]`
A dictionary with keys like `pairedDeviceCount`, `deviceIds`, or `nil` on failure.
|
healthCheck
()
|
Checks whether the test server is reachable.
Signature
```swift
public func healthCheck() -> Bool
```
Returns
`Bool`   `true` if the server responds to `/health`.
|
pairDevice
(
deviceType
)
|
Pairs a mock device of the specified type, powers it on, and sets it to "don" state.
Signature
```swift
public func pairDevice( deviceType: DeviceType) -> String?
```
Parameters
`deviceType: [DeviceType](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicetype)`
The device type to simulate. Defaults to `.rayBanMeta`.
Returns
`String?`
The paired device's identifier, or `nil` if pairing failed.
|
powerOff
(
deviceId
)
|
Powers off a mock device.
Signature
```swift
public func powerOff( deviceId: String) -> Bool
```
Parameters
`deviceId: String`
The identifier of the device to power off.
Returns
`Bool`   `true` if the command succeeded.
|
powerOn
(
deviceId
)
|
Powers on a mock device.
Signature
```swift
public func powerOn( deviceId: String) -> Bool
```
Parameters
`deviceId: String`
The identifier of the device to power on.
Returns
`Bool`   `true` if the command succeeded.
|
setCameraFeed
(
deviceId
, resourceName
, ext
)
|
Sets the camera feed video resource on a device.
Signature
```swift
public func setCameraFeed( deviceId: String, resourceName: String, ext: String) -> Bool
```
Parameters
`deviceId: String`
The identifier of the device.
`resourceName: String`
Bundle resource name for the video file.
`ext: String`
File extension (e.g. "mp4").
Returns
`Bool`   `true` if the command succeeded.
|
setCapturedImage
(
deviceId
, resourceName
, ext
)
|
Sets the captured image resource on a device.
Signature
```swift
public func setCapturedImage( deviceId: String, resourceName: String, ext: String) -> Bool
```
Parameters
`deviceId: String`
The identifier of the device.
`resourceName: String`
Bundle resource name for the image file.
`ext: String`
File extension (e.g. "png").
Returns
`Bool`   `true` if the command succeeded.
|
unfold
(
deviceId
)
|
Simulates unfolding mock glasses.
Signature
```swift
public func unfold( deviceId: String) -> Bool
```
Parameters
`deviceId: String`
The identifier of the glasses to unfold.
Returns
`Bool`   `true` if the command succeeded.
|
unpairDevice
(
deviceId
)
|
Unpairs a mock device.
Signature
```swift
public func unpairDevice( deviceId: String) -> Bool
```
Parameters
`deviceId: String`
The identifier of the device to unpair.
Returns
`Bool`   `true` if the command succeeded.
|
waitForServer
(
timeout
)
|
Polls the health endpoint until the server responds or the timeout expires.
Signature
```swift
public func waitForServer( timeout: TimeInterval) -> Bool
```
Parameters
`timeout: TimeInterval`
Maximum time to wait for the server.
Returns
`Bool`   `true` if the server became reachable within the timeout.
|
