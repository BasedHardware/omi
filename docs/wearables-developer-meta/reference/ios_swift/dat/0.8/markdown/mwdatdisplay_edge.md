---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_edge
title: Edge Struct
scraped_at: 2026-07-03T14:24:28.123Z
---

# Edge Struct
Extends
OptionSet, Sendable
A set of edges for padding modifiers.
## Signature
```swift
struct Edge: OptionSet, Sendable
```
## Constructors
init
(
rawValue
)
|
Signature
```swift
public init( rawValue: UInt8)
```
Parameters
`rawValue: UInt8`
|
## Properties
all
: [Edge](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_edge)
|
All four edges.
|
bottom
|
The bottom edge.
|
horizontal
: [Edge](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_edge)
|
Both leading and trailing edges.
|
leading
|
The leading (start) edge.
|
rawValue
: UInt8
|
|
top
|
The top edge.
|
trailing
|
The trailing (end) edge.
|
vertical
: [Edge](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_edge)
|
Both top and bottom edges.
|
