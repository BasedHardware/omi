---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_wearablesinterface
title: WearablesInterface Extension
scraped_at: 2026-07-03T14:24:26.172Z
---

# WearablesInterface Extension
Extends
Sendable
The primary interface for Wearables Device Access Toolkit.
## Signature
```swift
protocol WearablesInterface: Sendable
```
## Properties
devices
: [DeviceIdentifier]
[Get]
|
The current list of devices available.
|
registrationState
: [RegistrationState](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_registrationstate)
[Get]
|
The current registration state of the user's devices. See [RegistrationState](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_registrationstate) for options.
|
## Functions
addDevicesListener
(
listener
)
|
Adds a listener to receive callbacks when the device list changes. The listener is immediately called with the current devices.
Signature
```swift
public func addDevicesListener(_ listener: @Sendable @escaping ([DeviceIdentifier]) -> Void) -> AnyListenerToken
```
Parameters
`_ listener: @Sendable @escaping ([[DeviceIdentifier](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_deviceidentifier)]) -> Void`
The callback to execute when the device list changes.
Returns
`[AnyListenerToken](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_anylistenertoken)`
A token that can be used to cancel the listener. When the token deinits the listener is also canceled.
|
addRegistrationStateListener
(
listener
)
|
Adds a listener to receive callbacks when the registration state changes. The listener is immediately called with the current state.
Signature
```swift
public func addRegistrationStateListener(_ listener: @Sendable @escaping (RegistrationState) -> Void) -> AnyListenerToken
```
Parameters
`_ listener: @Sendable @escaping ([RegistrationState](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_registrationstate)) -> Void`
The callback to execute when the registration state changes.
Returns
`[AnyListenerToken](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_anylistenertoken)`
A token that can be used to cancel the listener. When the token deinits the listener is also canceled.
|
checkPermissionStatus
(
permission
)
|
Checks if a specific permission is granted for the current application.
Signature
```swift
public func checkPermissionStatus(_ permission: Permission) -> PermissionStatus
```
Parameters
`_ permission: [Permission](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_permission)`
The type of permission to check.
Returns
`[PermissionStatus](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_permissionstatus)`   [PermissionStatus](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_permissionstatus) The status of the permission.
Throws
|
createSession
(
deviceSelector
)
|
Creates a new [DeviceSession](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesession) for the device resolved by the given selector.
Fails if a non-stopped session already exists for the resolved device. After the session has stopped or been released, a new one can be created. Call [DeviceSession.start()](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesession#start) to connect, then add capabilities such as `DeviceSession/addStream(config:)` once the session reaches [DeviceSessionState.started](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesessionstate#started).
Signature
```swift
public func createSession( deviceSelector: DeviceSelector) -> DeviceSession
```
Parameters
`deviceSelector: [DeviceSelector](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_deviceselector)`
The selector that determines which device to connect to.
Returns
`[DeviceSession](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesession)`
A new [DeviceSession](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesession).
Throws
|
deviceForIdentifier
(
identifier
)
|
Fetch the underlying [Device](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_device) object for a given [DeviceIdentifier](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_deviceidentifier).
Signature
```swift
public func deviceForIdentifier(_ identifier: DeviceIdentifier) -> Device?
```
Parameters
`_ identifier: [DeviceIdentifier](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_deviceidentifier)`
The device identifier to fetch.
Returns
`[Device?](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_device)`
The [Device](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_device) object for the given device identifier.
|
devicesStream
()
|
Creates an `AsyncStream` for observing device list changes.
Signature
```swift
public func devicesStream() -> AsyncStream
```
Returns
`AsyncStream `
|
deviceStateStream
(
identifier
)
|
Creates an `AsyncStream` for observing device state changes on a specific device.
Signature
```swift
public func deviceStateStream(for identifier: DeviceIdentifier) -> AsyncStream
```
Parameters
`for identifier: [DeviceIdentifier](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_deviceidentifier)`
The device to observe.
Returns
`AsyncStream `
A stream that yields [DeviceState](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicestate) values when the device state changes (e.g. thermal level).
|
handleUrl
(
url
)
|
Handles callback URLs from the Meta AI app during registration and permission flows.
This method must be called when your app receives a URL callback after the user completes an action in the Meta AI app. This includes callbacks from [startRegistration()](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_wearablesinterface#startRegistration), [startUnregistration()](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_wearablesinterface#startUnregistration), and permission requests.
The SDK will determine if the URL is relevant to the Wearables Device Access Toolkit. If not relevant, the method returns `false` without throwing an error.
## Platform Flow On iOS, the Meta AI app returns to your app via a URL scheme callback. You must: 1. Configure your app's URL schemes in Info.plist 2. Implement URL handling in your app delegate or scene delegate 3. Call this method with the received URL
Signature
```swift
public func handleUrl(_ url: URL) -> Bool
```
Parameters
`_ url: URL`
The incoming URL to handle.
Returns
`Bool`   `true` if the URL was handled by the Wearables Device Access Toolkit, `false` if it's not relevant to the Wearables Device Access Toolkit.
Throws
|
openDATGlassesAppUpdate
()
|
Opens the DAT glasses app update screen in the Meta AI app.
Developer mode apps are routed to the developer app management surface, while production apps are routed to the app connections page for the configured Meta app identifier.
Signature
```swift
public func openDATGlassesAppUpdate()
```
Throws
|
openFirmwareUpdate
()
|
Opens the firmware update screen in the Meta AI app for the connected device.
This method launches the Meta AI app and navigates directly to the firmware update screen. The user can then check for and install any available firmware updates.
Signature
```swift
public func openFirmwareUpdate()
```
Throws
|
registrationStateStream
()
|
Creates an `AsyncStream` for observing registration state changes.
Signature
```swift
public func registrationStateStream() -> AsyncStream
```
Returns
`AsyncStream `
|
requestPermission
(
permission
)
|
Requests a specific permission on AI glasses.
This method opens the Meta AI app where the user completes the permission request flow. After the user responds in the Meta AI app, your app will receive a callback URL that must be passed to [handleUrl(_:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_wearablesinterface#handleUrl) to complete the permission request.
Signature
```swift
public func requestPermission(_ permission: Permission) -> PermissionStatus
```
Parameters
`_ permission: [Permission](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_permission)`
The type of permission to request.
Returns
`[PermissionStatus](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_permissionstatus)`
The [PermissionStatus](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_permissionstatus) after the user responds.
Throws
|
startRegistration
()
|
Initiates the registration process with AI glasses.
This method opens the Meta AI app where the user completes the registration flow. After the user completes the flow in the Meta AI app, your app will receive a callback URL that must be passed to [handleUrl(_:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_wearablesinterface#handleUrl) to complete the registration.
The [registrationState](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_wearablesinterface#registrationState) property will be updated throughout the registration process.
Signature
```swift
public func startRegistration()
```
Throws
|
startUnregistration
()
|
Initiates the unregistration process with AI glasses.
This method opens the Meta AI app where the user completes the unregistration flow. After the user completes the flow in the Meta AI app, your app will receive a callback URL that must be passed to [handleUrl(_:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_wearablesinterface#handleUrl) to complete the unregistration.
The [registrationState](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_wearablesinterface#registrationState) property will be updated throughout the unregistration process.
Signature
```swift
public func startUnregistration()
```
Throws
|
