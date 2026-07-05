---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatmockdevice_mockcaptouchkit
title: MockCaptouchKit Protocol
scraped_at: 2026-07-03T14:24:34.351Z
---

# MockCaptouchKit Protocol
Extends
Sendable
Public interface for simulating captouch gestures on a mock device.
This interface allows test code to simulate captouch inputs that the device firmware would normally send during an active session. These gestures are delivered to the SDK's session and can trigger session behaviors like pause/resume or stop.
Usage example:
```swift
let mockDevice = MockDeviceKit.shared.pairGlasses(type: .rayBanMeta) mockDevice?.powerOn() mockDevice?.don() mockDevice?.unfold() // Start a session, then simulate a tap gesture mockDevice?.services.captouch.tap()
```
## Signature
```swift
protocol MockCaptouchKit: Sendable
```
## Functions
tap
()
|
Simulate a single tap gesture on the device's capacitive touch sensor (1-finger captouch).
The SDK's session will toggle between paused and running states, matching the behavior of a physical single tap on the glasses.
Requires an active session — if no session is running, this call is a no-op with a warning log.
Signature
```swift
public func tap()
```
|
tapAndHold
()
|
Simulate a tap-and-hold gesture on the device's capacitive touch sensor (1-finger captouch).
This stops the active session, matching the behavior of a physical tap-and-hold on the glasses which terminates the streaming session.
Requires an active session — if no session is running, this call is a no-op with a warning log.
Signature
```swift
public func tapAndHold()
```
|
