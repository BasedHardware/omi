---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_alignment
title: Alignment Enum
scraped_at: 2026-07-03T14:24:26.521Z
---

# Alignment Enum
Extends
Sendable
Alignment options for positioning children within a [FlexBox](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_flexbox) layout.
Controls how children are aligned along the main axis (`alignment`) or cross axis (`crossAlignment`), and how individual children override their parent's cross-axis alignment via `ViewComponent/alignSelf(_:)`.
## Signature
```swift
enum Alignment: Sendable
```
## Enumeration Constants
Member | Description |
start
|
Align children to the start of the axis.
|
center
|
Center children along the axis.
|
end
|
Align children to the end of the axis.
|
stretch
|
Stretch children to fill the available space along the cross axis.
|
