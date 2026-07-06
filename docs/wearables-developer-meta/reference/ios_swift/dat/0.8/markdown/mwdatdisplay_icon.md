---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_icon
title: Icon Struct
scraped_at: 2026-07-03T14:24:30.263Z
---

# Icon Struct
Extends
ViewComponentSerializable, Sendable
An icon component displayed on the wearable.
Icons are referenced by name and rendered using the device's built-in icon set.
## Signature
```swift
struct Icon: ViewComponentSerializable, Sendable
```
## Constructors
init
(
name
, style
)
|
Creates an icon with the given name and style.
Signature
```swift
public init( name: IconName, style: IconStyle)
```
Parameters
`name: [IconName](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_iconname)`
The icon name.
`style: [IconStyle](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_iconstyle)`
Whether the icon is filled or outlined. Defaults to [IconStyle.filled](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_iconstyle#filled).
|
## Properties
name
: [IconName](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_iconname)
|
The icon name.
|
style
: [IconStyle](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_iconstyle)
|
Whether the icon is filled or outlined.
|
