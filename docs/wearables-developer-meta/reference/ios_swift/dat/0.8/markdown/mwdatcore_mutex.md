---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_mutex
title: Mutex Struct
scraped_at: 2026-07-03T14:24:20.847Z
---

# Mutex Struct
Extends
~Copyable
## Signature
```swift
struct Mutex: ~Copyable
```
## Constructors
init
(
initialValue
)
|
Signature
```swift
public init(_ initialValue: sending Value)
```
Parameters
`_ initialValue: sending Value`
|
## Functions
withLock
(
body
)
|
Signature
```swift
public func withLock (_ body: (inout sending Value) throws(E) -> sending Result) -> sending Result
```
Parameters
`_ body: (inout sending Value) throws(E) -> sending Result`
Returns
`sending Result`
|
