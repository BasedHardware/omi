---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_anylistenertoken
title: AnyListenerToken Protocol
scraped_at: 2026-07-03T14:24:16.039Z
---

# AnyListenerToken Protocol
Extends
Sendable
A token that can be used to cancel a listener subscription. When the token is no longer referenced, the listener is automatically canceled.
## Signature
```swift
protocol AnyListenerToken: Sendable
```
## Functions
cancel
()
|
Cancels the listener subscription asynchronously.
Signature
```swift
public func cancel()
```
|
