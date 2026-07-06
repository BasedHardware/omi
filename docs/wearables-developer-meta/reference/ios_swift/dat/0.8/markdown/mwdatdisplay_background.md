---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_background
title: Background Enum
scraped_at: 2026-07-03T14:24:25.374Z
---

# Background Enum
Extends
Sendable
Background-style options for [FlexBox](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_flexbox).
Maps to the `background` oneof on the wire: `.card` renders a WDS StaticContainer-style background; `.none` renders no background.
## Signature
```swift
enum Background: Sendable
```
## Enumeration Constants
Member | Description |
none
|
No background.
|
card
|
WDS card background with rounded corners.
|
