---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_device
title: Device Class
scraped_at: 2026-07-03T14:24:18.040Z
---

# Device Class
Extends
Sendable
Modifiers:
const AI glasses accessible through the Wearables Device Access Toolkit.
## Signature
```swift
class Device: Sendable
```
## Properties
deviceUUID
: UUID
[Get]
|
This UUID is persisted across app launches and used for Airship scope registration. Note: This differs from `identifier` which comes from the server manifest.
|
identifier
: [DeviceIdentifier](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_deviceidentifier)
|
The unique identifier for this device.
|
linkState
: [LinkState](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_linkstate)
[Get]
|
The current connection state of the device.
|
name
: String
[Get]
|
The human-readable device name, or empty string if unavailable.
|
## Functions
addCompatibilityListener
(
listener
)
|
Adds a listener to receive notifications when the device's compatibility changes.
Signature
```swift
public func addCompatibilityListener(_ listener: @escaping @Sendable (Compatibility) -> Void) -> AnyListenerToken
```
Parameters
`_ listener: @escaping @Sendable ([Compatibility](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_compatibility)) -> Void`
The callback to execute when the compatibility changes.
Returns
`[AnyListenerToken](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_anylistenertoken)`
A token that can be used to cancel the listener.
|
addLinkStateListener
(
listener
)
|
Adds a listener to receive notifications when the device's link state changes.
Signature
```swift
public func addLinkStateListener(_ listener: @escaping @Sendable (LinkState) -> Void) -> AnyListenerToken
```
Parameters
`_ listener: @escaping @Sendable ([LinkState](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_linkstate)) -> Void`
The callback to execute when the link state changes.
Returns
`[AnyListenerToken](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_anylistenertoken)`
A token that can be used to cancel the listener.
|
compatibility
()
|
Returns true if the version of this device is compatible with the Wearables Device Access Toolkit.
Signature
```swift
public func compatibility() -> Compatibility
```
Returns
`[Compatibility](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_compatibility)`
|
deviceType
()
|
Returns the type of this device (e.g., Ray-Ban Meta).
Signature
```swift
public func deviceType() -> DeviceType
```
Returns
`[DeviceType](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicetype)`
The device type identifier.
|
nameOrId
()
|
Returns the device name if available, otherwise returns the device identifier. This provides a fallback for display purposes when the device name is not set.
Signature
```swift
public func nameOrId() -> String
```
Returns
`String`
The device name or identifier as a fallback.
|
supportsDisplay
()
|
Returns whether this device has a built-in display.
Signature
```swift
public func supportsDisplay() -> Bool
```
Returns
`Bool`   `true` if the device type supports a display, `false` otherwise.
|
