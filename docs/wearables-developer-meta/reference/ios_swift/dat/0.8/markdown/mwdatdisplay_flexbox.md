---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_flexbox
title: FlexBox Struct
scraped_at: 2026-07-03T14:24:29.802Z
---

# FlexBox Struct
Extends
ViewComponentSerializable, RootViewSerializable, Sendable
A flex layout container that arranges children along a configurable axis.
`FlexBox` is the root-level display component. Create a `FlexBox` and pass it to [Display.send(_:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_display#send) to show content on glasses.
`FlexBox` is also the only layout type that accepts the layout-shape modifiers [flexGrow(_:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_flexbox#flexGrow), [flexShrink(_:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_flexbox#flexShrink), [alignSelf(_:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_flexbox#alignSelf), `padding(_:)-3lpgz`, [background(_:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_flexbox#background), and [onTap(_:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_flexbox#onTap) — each returns a copy of the same `FlexBox` with one field changed, never wrapping it in another container.
## Signature
```swift
struct FlexBox: ViewComponentSerializable, RootViewSerializable, Sendable
```
## Constructors
init
(
direction
, spacing
, alignment
, crossAlignment
, wrap
, padding
, content
)
|
Creates a FlexBox with children built using the result builder DSL.
Signature
```swift
public init( direction: Direction, spacing: CGFloat, alignment: Alignment, crossAlignment: Alignment, wrap: Bool, padding: EdgeInsets?, content: () -> [any ViewComponent])
```
Parameters
`direction: [Direction](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_direction)`
The layout direction for children. Defaults to [Direction.column](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_direction#column).
`spacing: CGFloat`
Spacing in dp between children. Defaults to `0`.
`alignment: [Alignment](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_alignment)`
Alignment of children along the main axis. Defaults to [Alignment.start](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_alignment#start).
`crossAlignment: [Alignment](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_alignment)`
Alignment of children along the cross axis. Defaults to [Alignment.start](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_alignment#start).
`wrap: Bool`
Whether children should wrap to the next line. Defaults to `false`.
`padding: [EdgeInsets?](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_edgeinsets)`
Padding applied to the edges of the container. Defaults to `nil`.
`content: () -> [any [ViewComponent](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_viewcomponent)]`
A builder block for adding child components.
|
## Properties
alignment
: [Alignment](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_alignment)
|
Alignment of children along the main axis.
|
alignSelf
: Alignment?
|
Per-child cross-axis alignment override applied when this FlexBox is a child of another FlexBox.
|
background
: [Background](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_background)
|
Background style for this FlexBox. Defaults to [Background.none](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_background#none). Note: when [onTap(_:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_flexbox#onTap) is set, the renderer applies its own interactive background regardless of this field.
|
children
: [any ViewComponent]
|
The child components arranged within this flex layout.
|
crossAlignment
: [Alignment](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_alignment)
|
Alignment of children along the cross axis.
|
direction
: [Direction](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_direction)
|
The layout direction for children.
|
flexGrow
: Float
|
Flex-grow factor applied when this FlexBox is itself a child of another FlexBox.
|
flexShrink
: Float
|
Flex-shrink factor applied when this FlexBox is itself a child of another FlexBox.
|
onClick
: (@Sendable () -> Void)?
|
Optional callback invoked when this FlexBox is tapped on the wearable. Set via [onTap(_:)](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_flexbox#onTap). The renderer automatically draws an interactive background for tappable FlexBoxes.
|
padding
: EdgeInsets?
|
Padding applied to the edges of the flex container.
|
spacing
: CGFloat
|
Spacing in dp between children.
|
wrap
: Bool
|
Whether children should wrap to the next line when they exceed the container.
|
## Functions
alignSelf
(
value
)
|
Overrides the cross-axis alignment for this FlexBox.
Signature
```swift
public func alignSelf(_ value: Alignment) -> FlexBox
```
Parameters
`_ value: [Alignment](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_alignment)`
Returns
`[FlexBox](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_flexbox)`
|
background
(
value
)
|
Sets the background style for this FlexBox.
Signature
```swift
public func background(_ value: Background) -> FlexBox
```
Parameters
`_ value: [Background](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_background)`
Returns
`[FlexBox](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_flexbox)`
|
flexGrow
(
value
)
|
Sets the flex-grow factor for this FlexBox.
Signature
```swift
public func flexGrow(_ value: Float) -> FlexBox
```
Parameters
`_ value: Float`
Returns
`[FlexBox](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_flexbox)`
|
flexShrink
(
value
)
|
Sets the flex-shrink factor for this FlexBox.
Signature
```swift
public func flexShrink(_ value: Float) -> FlexBox
```
Parameters
`_ value: Float`
Returns
`[FlexBox](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_flexbox)`
|
onTap
(
handler
)
|
Adds a tap handler.
Signature
```swift
public func onTap(_ handler: @escaping @Sendable () -> Void) -> FlexBox
```
Parameters
`_ handler: @escaping @Sendable () -> Void`
Returns
`[FlexBox](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_flexbox)`
|
padding
(
value
)
|
Sets edge insets as the FlexBox padding.
Signature
```swift
public func padding(_ value: CGFloat) -> FlexBox
```
Parameters
`_ value: CGFloat`
Returns
`[FlexBox](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_flexbox)`
|
padding
(
edges
, value
)
|
Sets padding on a specific subset of edges.
Signature
```swift
public func padding(_ edges: Edge, _ value: CGFloat) -> FlexBox
```
Parameters
`_ edges: [Edge](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_edge)`
`_ value: CGFloat`
Returns
`[FlexBox](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatdisplay_flexbox)`
|
