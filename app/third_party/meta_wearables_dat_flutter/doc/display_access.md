# Display Access

Display Access renders a **declarative UI tree** on the in-lens display of
Ray-Ban Display glasses. You build a component tree in Dart, send it to the
glasses, and react to touchpad taps / button clicks / video playback events
through callbacks — the native bridge handles the round trip.

This wraps Meta DAT 0.7.0's `MWDATDisplay` (iOS) / `mwdat-display` (Android)
module.

## Prerequisites

1. DAT **0.7.0+** and a Display-capable device (Ray-Ban Display).
2. Registration is complete (`RegistrationState.registered`).
3. On Android, Bluetooth / Internet permissions granted via
   `requestAndroidPermissions()`.

## Lifecycle

```dart
await MetaWearablesDat.startDisplaySession();      // attach + start display
MetaWearablesDat.displayStateStream().listen((s) {
  // DisplayState.starting | started | stopping | stopped
});

await MetaWearablesDat.sendDisplayView(myView);    // render a tree

await MetaWearablesDat.stopDisplaySession();       // detach + tear down
```

`startDisplaySession({String? deviceUUID})` creates a `DeviceSession` (the
first paired device by default), attaches the `Display` capability, and waits
for it to reach `DisplayState.started`. Pass `deviceUUID` to target a specific
device.

## Building a view

The view tree is a sealed `DisplayNode` hierarchy. Every node serializes to a
platform-channel map via `toJson()`; you rarely call that yourself — pass the
root to `sendDisplayView`.

```dart
final view = FlexBox(
  spacing: 12,
  children: [
    FlexBox(
      padding: 24,
      background: FlexBoxBackground.card,
      onTap: () => openDetail(),
      children: [
        DisplayImage(
          'https://example.com/oil.png',
          sizePreset: DisplayImageSize.fill,
          cornerRadius: DisplayCornerRadius.medium,
        ),
        DisplayText('Oil change', style: DisplayTextStyle.heading),
        DisplayText(
          'Easy • 45 min',
          style: DisplayTextStyle.meta,
          color: DisplayTextColor.secondary,
        ),
      ],
    ),
    FlexBox(
      direction: DisplayDirection.row,
      spacing: 8,
      alignment: DisplayAlignment.center,
      crossAlignment: DisplayAlignment.center,
      wrap: true,
      children: [
        DisplayButton(label: 'Back', onClick: () => goBack()),
        DisplayButton(
          label: 'Next',
          iconName: DisplayIconName.triangleRightVerticalLine,
          onClick: () => goNext(),
        ),
      ],
    ),
  ],
);

await MetaWearablesDat.sendDisplayView(view);
```

### Components

| Dart model | Fields |
| --- | --- |
| `FlexBox` | `children`, `direction`, `spacing`, `padding`, `background`, `alignment`, `crossAlignment`, `wrap`, `flexGrow`, `onTap` |
| `DisplayText` | `text`, `style` (`heading` / `body` / `meta`), `color` (`primary` / `secondary`) |
| `DisplayImage` | `uri`, `sizePreset`, `cornerRadius` |
| `DisplayButton` | `label`, `style` (`primary` / `secondary`), `iconName`, `onClick` |
| `DisplayIcon` | `name` (`DisplayIconName`) |
| `VideoPlayer` | `uri`, `codec`, `onPlaybackEvent` (root-only) |

### Layout enums

- `DisplayDirection`: `row`, `column`.
- `DisplayAlignment`: `start`, `center`, `end`, `spaceBetween`,
  `spaceAround`, `spaceEvenly` (main and cross axes).
- `FlexBoxBackground`: `none`, `card`.
- `DisplayCornerRadius`: `none`, `small`, `medium`, `large` (large collapses
  to medium on devices that don't support it).

## Callbacks

`onTap` (FlexBox), `onClick` (Button), and `onPlaybackEvent` (VideoPlayer) are
plain Dart closures. During serialization each gets a generated id; native
interaction events arrive on the `display_events` channel as
`{callbackId, type, event?}` and are dispatched back to the right closure.

The callback table is **rebuilt on every `sendDisplayView`**, so ids only
resolve for the view currently on the glasses. Send a new view in response to
a callback to drive navigation:

```dart
DisplayView listView() => FlexBox(
  children: [
    for (final t in tutorials)
      FlexBox(
        background: FlexBoxBackground.card,
        onTap: () => sendDetail(t),   // re-send a new tree on tap
        children: [DisplayText(t.title)],
      ),
  ],
);
```

## Video

`VideoPlayer` is a **root** view, not a nestable component. Playback starts
automatically once the video is sent; `onPlaybackEvent` reports transitions:

```dart
await MetaWearablesDat.sendDisplayView(
  VideoPlayer(
    'https://example.com/clip.mp4',
    onPlaybackEvent: (event) {
      switch (event.type) {
        case DisplayPlaybackEventType.ended:
          showNextStep();
        case _:
          break;
      }
    },
  ),
);
```

`DisplayPlaybackEventType`: `playing`, `paused`, `ended`, `stopped`, `error`,
`unknown`.

## Channels

| Channel | Type | Payload |
| --- | --- | --- |
| `meta_wearables_dat_flutter/display_state` | EventChannel | `DisplayState` (int) |
| `meta_wearables_dat_flutter/display_events` | EventChannel | `{callbackId, type, event?}` |

`sendDisplayView` / `startDisplaySession` / `stopDisplaySession` go over the
shared `meta_wearables_dat_flutter` MethodChannel.

## Errors

DAT 0.7.0 adds `DeviceSessionError.datAppOnTheGlassesUpdateRequired`
(`error.isDatAppUpdateRequired`), surfaced when the on-glasses DAT app needs an
update before a display session can start.

## See also

- Sample app: [`samples/display_access/`](../samples/display_access/) — a full
  port of Meta's "Car Maintenance" Display sample.
- Skill: [`.claude/skills/display-access.md`](../.claude/skills/display-access.md).
- Meta developer docs: <https://wearables.developer.meta.com/docs/develop/>.
