---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_edgeinsets
title: EdgeInsets Struct
scraped_at: 2026-07-03T14:24:29.441Z
---

# EdgeInsets Struct
Extends
Sendable
Edge inset values for padding, in density-independent pixels (dp).
## Signature
```swift
struct EdgeInsets: Sendable
```
## Constructors
init
(
top
, bottom
, leading
, trailing
)
|
Creates edge insets with the specified values.
Signature
```swift
public init( top: CGFloat, bottom: CGFloat, leading: CGFloat, trailing: CGFloat)
```
Parameters
`top: CGFloat`
Padding for the top edge. Defaults to `0`.
`bottom: CGFloat`
Padding for the bottom edge. Defaults to `0`.
`leading: CGFloat`
Padding for the leading edge. Defaults to `0`.
`trailing: CGFloat`
Padding for the trailing edge. Defaults to `0`.
|
init
(
value
)
|
Creates edge insets with uniform padding on all sides.
Signature
```swift
public init(all value: CGFloat)
```
Parameters
`all value: CGFloat`
|
## Properties
bottom
: CGFloat
|
Padding for the bottom edge in dp.
|
leading
: CGFloat
|
Padding for the leading (start) edge in dp.
|
top
: CGFloat
|
Padding for the top edge in dp.
|
trailing
: CGFloat
|
Padding for the trailing (end) edge in dp.
|
