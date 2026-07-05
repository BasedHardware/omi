---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesession
title: DeviceSession Class
scraped_at: 2026-07-03T14:24:19.785Z
---

# DeviceSession Class
Extends
Sendable
Modifiers:
const A session representing a connection to a specific wearable device.
`DeviceSession` manages the lifecycle of a connection to a device and serves as the parent for capabilities (e.g., streaming, display). Create sessions via [WearablesInterface.createSession(deviceSelector:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_wearablesinterface#createSession).
## Lifecycle
1. Create via `Wearables.shared.createSession(deviceSelector:)`
2. Observe [statePublisher](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesession#statePublisher) or [stateStream()](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesession#stateStream) for state changes
3. Call [start()](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesession#start) to connect
4. Attach capabilities (e.g., `addStream()`)
5. Call [stop()](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesession#stop) to disconnect (cascades to all attached capabilities)
Sessions are not reusable — after reaching [DeviceSessionState.stopped](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesessionstate#stopped), create a new session via the factory.
## Signature
```swift
class DeviceSession: Sendable
```
## Properties
deviceId
: [DeviceIdentifier](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_deviceidentifier)
|
The identifier of the device this session is connected to.
|
errorPublisher
: any Announcer<DeviceSessionError>
[Get]
|
An announcer that emits [DeviceSessionError](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesessionerror) events.
|
state
: [DeviceSessionState](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesessionstate)
[Get]
|
The current state of this session.
|
statePublisher
: any Announcer<DeviceSessionState>
[Get]
|
An announcer that emits [DeviceSessionState](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesessionstate) changes.
|
## Functions
errorStream
()
|
Creates an `AsyncStream` for observing session errors.
Signature
```swift
public func errorStream() -> AsyncStream
```
Returns
`AsyncStream `
|
start
()
|
Starts the session, connecting to the device.
Validates that the device is available, compatible, and connected before transitioning to [DeviceSessionState.starting](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesessionstate#starting). If validation fails, the session stays in [DeviceSessionState.idle](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesessionstate#idle) and the error is thrown, allowing the caller to retry later.
Signature
```swift
public func start()
```
Throws
|
stateStream
()
|
Creates an `AsyncStream` for observing session state changes.
Create the stream before calling [start()](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesession#start) to avoid missing the initial state transitions.
Signature
```swift
public func stateStream() -> AsyncStream
```
Returns
`AsyncStream `
|
stop
()
|
Stops the session, disconnecting from the device and cascading stop to all attached capabilities.
This is a sync fire-and-forget call. Observe [statePublisher](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesession#statePublisher) or [stateStream()](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesession#stateStream) for the transition to [DeviceSessionState.stopped](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_devicesessionstate#stopped). Calling stop on an already stopped or stopping session is a no-op.
Signature
```swift
public func stop()
```
|
