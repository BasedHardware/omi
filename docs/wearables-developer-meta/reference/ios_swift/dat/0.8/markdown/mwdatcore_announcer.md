---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_announcer
title: Announcer Protocol
scraped_at: 2026-07-03T14:24:15.899Z
---

# Announcer Protocol
A protocol for objects that can announce events to registered listeners.
## Signature
```swift
protocol Announcer
```
## Functions
listen
(
listener
)
|
Registers a listener for events of type T.
Signature
```swift
public func listen(_ listener: @Sendable @escaping (T) -> Void) -> AnyListenerToken
```
Parameters
`_ listener: @Sendable @escaping (T) -> Void`
The callback to execute when an event occurs.
Returns
`[AnyListenerToken](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_anylistenertoken)`
A token that can be used to cancel the listener.
|
