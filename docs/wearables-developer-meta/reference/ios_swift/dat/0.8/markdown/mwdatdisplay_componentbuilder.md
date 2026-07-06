---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_componentbuilder
title: ComponentBuilder Struct
scraped_at: 2026-07-03T14:24:27.500Z
---

# ComponentBuilder Struct
A result builder for composing view components inside a [FlexBox](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_flexbox).
## Signature
```swift
struct ComponentBuilder
```
## Functions
buildArray
(
components
)
|
Signature
```swift
public static func buildArray(_ components: [[any ViewComponent]]) -> [any ViewComponent]
```
Parameters
`_ components: [[any [ViewComponent](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_viewcomponent)]]`
Returns
`[any [ViewComponent](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_viewcomponent)]`
|
buildBlock
(
components
)
|
Signature
```swift
public static func buildBlock(_ components: ]...) -> [any ViewComponent]
```
Parameters
`_ components: ]...`
Returns
`[any [ViewComponent](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_viewcomponent)]`
|
buildEither
(
component
)
|
Signature
```swift
public static func buildEither(first component: [any ViewComponent]) -> [any ViewComponent]
```
Parameters
`first component: [any [ViewComponent](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_viewcomponent)]`
Returns
`[any [ViewComponent](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_viewcomponent)]`
|
buildEither
(
component
)
|
Signature
```swift
public static func buildEither(second component: [any ViewComponent]) -> [any ViewComponent]
```
Parameters
`second component: [any [ViewComponent](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_viewcomponent)]`
Returns
`[any [ViewComponent](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_viewcomponent)]`
|
buildExpression
(
expression
)
|
Signature
```swift
public static func buildExpression(_ expression: any ViewComponent) -> [any ViewComponent]
```
Parameters
`_ expression: any [ViewComponent](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_viewcomponent)`
Returns
`[any [ViewComponent](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_viewcomponent)]`
|
buildOptional
(
component
)
|
Signature
```swift
public static func buildOptional(_ component: [any ViewComponent]?) -> [any ViewComponent]
```
Parameters
`_ component: [any [ViewComponent](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_viewcomponent)]`
Returns
`[any [ViewComponent](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_viewcomponent)]`
|
