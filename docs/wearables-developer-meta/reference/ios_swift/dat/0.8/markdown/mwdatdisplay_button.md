---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_button
title: Button Struct
scraped_at: 2026-07-03T14:24:25.398Z
---

# Button Struct
Extends
ViewComponentSerializable, Sendable
A tappable button component displayed on the wearable.
Buttons can optionally include an icon alongside the label and respond to tap events via [onClick](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_button#onClick).
## Signature
```swift
struct Button: ViewComponentSerializable, Sendable
```
## Constructors
init
(
label
, style
, iconName
, onClick
)
|
Creates a button with the given label and configuration.
Signature
```swift
public init( label: String, style: ButtonStyle, iconName: IconName?, onClick: (@Sendable () -> Void)?)
```
Parameters
`label: String`
The button text.
`style: [ButtonStyle](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_buttonstyle)`
Visual style preset for the button. Defaults to [ButtonStyle.primary](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_buttonstyle#primary).
`iconName: [IconName?](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_iconname)`
Optional icon name to display alongside the label.
`onClick: (@Sendable () -> Void)`
Optional callback invoked when the button is tapped.
|
## Properties
iconName
: IconName?
|
Optional icon name to display alongside the label.
|
label
: String
|
The button text.
|
onClick
: (@Sendable () -> Void)?
|
Optional callback invoked when the button is tapped on the wearable.
|
style
: [ButtonStyle](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_buttonstyle)
|
Visual style preset for the button.
|
