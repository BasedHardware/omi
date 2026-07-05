---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_text
title: Text Struct
scraped_at: 2026-07-03T14:24:32.278Z
---

# Text Struct
Extends
ViewComponentSerializable, Sendable
A text component displayed on the wearable.
## Signature
```swift
struct Text: ViewComponentSerializable, Sendable
```
## Constructors
init
(
content
, style
, color
)
|
Creates a text component with the given content and styling.
Signature
```swift
public init(_ content: String, style: TextStyle, color: TextColor)
```
Parameters
`_ content: String`
The text string to display.
`style: [TextStyle](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_textstyle)`
Typography preset for the text. Defaults to [TextStyle.body](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_textstyle#body).
`color: [TextColor](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_textcolor)`
Color preset for the text. Defaults to [TextColor.primary](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_textcolor#primary).
|
## Properties
color
: [TextColor](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_textcolor)
|
Color preset for the text.
|
content
: String
|
The text string to display.
|
style
: [TextStyle](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_textstyle)
|
Typography preset for the text.
|
