import 'package:meta_wearables_dat_flutter/src/models/display/display_playback_event.dart';

/// Layout direction of a [FlexBox]'s children.
enum DisplayDirection {
  /// Lay children out horizontally.
  row('row'),

  /// Lay children out vertically.
  column('column');

  const DisplayDirection(this.wireName);

  /// The string used on the platform channel.
  final String wireName;
}

/// Main-axis / cross-axis alignment of a [FlexBox]'s children.
///
/// Used for both `alignment` (main axis) and `crossAlignment` (cross axis).
enum DisplayAlignment {
  /// Pack children towards the start.
  start('start'),

  /// Center children.
  center('center'),

  /// Pack children towards the end.
  end('end'),

  /// Distribute free space between children.
  spaceBetween('spaceBetween'),

  /// Distribute free space around children.
  spaceAround('spaceAround'),

  /// Distribute free space evenly around children.
  spaceEvenly('spaceEvenly');

  const DisplayAlignment(this.wireName);

  /// The string used on the platform channel.
  final String wireName;
}

/// Typographic style of a [DisplayText].
enum DisplayTextStyle {
  /// Prominent heading text.
  heading('heading'),

  /// Default body text.
  body('body'),

  /// De-emphasised metadata text.
  meta('meta');

  const DisplayTextStyle(this.wireName);

  /// The string used on the platform channel.
  final String wireName;
}

/// Color role of a [DisplayText].
enum DisplayTextColor {
  /// The primary (default) text color.
  primary('primary'),

  /// A de-emphasised secondary text color.
  secondary('secondary');

  const DisplayTextColor(this.wireName);

  /// The string used on the platform channel.
  final String wireName;
}

/// Sizing preset for a [DisplayImage].
enum DisplayImageSize {
  /// Fill the available width, preserving aspect ratio.
  fill('fill');

  const DisplayImageSize(this.wireName);

  /// The string used on the platform channel.
  final String wireName;
}

/// Corner-radius preset applied to a [DisplayImage] or [FlexBox].
enum DisplayCornerRadius {
  /// Square corners.
  none('none'),

  /// A small corner radius.
  small('small'),

  /// A medium corner radius.
  medium('medium'),

  /// A large corner radius.
  large('large');

  const DisplayCornerRadius(this.wireName);

  /// The string used on the platform channel.
  final String wireName;
}

/// Visual style of a [DisplayButton].
enum DisplayButtonStyle {
  /// The primary, high-emphasis button style.
  primary('primary'),

  /// The secondary, lower-emphasis button style.
  secondary('secondary');

  const DisplayButtonStyle(this.wireName);

  /// The string used on the platform channel.
  final String wireName;
}

/// Built-in glyph rendered by a [DisplayIcon] or shown inside a
/// [DisplayButton].
///
/// Names mirror Meta's `IconName` (Android) / `Icon` (iOS) enums; the wire
/// token is normalised to camelCase and mapped back to each platform's enum
/// natively.
enum DisplayIconName {
  /// A checkmark glyph.
  checkmark('checkmark'),

  /// A video-camera glyph.
  videoCamera('videoCamera'),

  /// A left-pointing triangle (with a vertical line).
  triangleLeftVerticalLine('triangleLeftVerticalLine'),

  /// A right-pointing triangle (with a vertical line).
  triangleRightVerticalLine('triangleRightVerticalLine');

  const DisplayIconName(this.wireName);

  /// The string used on the platform channel.
  final String wireName;
}

/// Container background preset for a [FlexBox].
enum FlexBoxBackground {
  /// No background.
  none('none'),

  /// The standard "card" surface background.
  card('card');

  const FlexBoxBackground(this.wireName);

  /// The string used on the platform channel.
  final String wireName;
}

/// Container codec hint for a [VideoPlayer].
enum DisplayVideoCodec {
  /// An MP4-contained video.
  mp4('mp4');

  const DisplayVideoCodec(this.wireName);

  /// The string used on the platform channel.
  final String wireName;
}

/// Collects the callbacks attached to a display view tree and assigns each a
/// stable id so they can be serialized and later dispatched from native
/// tap / click / playback events.
///
/// One table is built per `sendDisplayView` call; ids are only meaningful for
/// the view currently shown on the glasses.
class DisplayCallbackTable {
  final Map<String, void Function()> _voidCallbacks = <String, void Function()>{};
  final Map<String, void Function(DisplayPlaybackEvent)> _playbackCallbacks =
      <String, void Function(DisplayPlaybackEvent)>{};
  int _next = 0;

  /// Registers a no-argument [callback] (a tap / click) and returns its id, or
  /// `null` when [callback] is `null`.
  String? registerTap(void Function()? callback) {
    if (callback == null) return null;
    final id = 'cb${_next++}';
    _voidCallbacks[id] = callback;
    return id;
  }

  /// Registers a playback [callback] and returns its id, or `null` when
  /// [callback] is `null`.
  String? registerPlayback(void Function(DisplayPlaybackEvent)? callback) {
    if (callback == null) return null;
    final id = 'cb${_next++}';
    _playbackCallbacks[id] = callback;
    return id;
  }

  /// Whether no callbacks were registered.
  bool get isEmpty => _voidCallbacks.isEmpty && _playbackCallbacks.isEmpty;

  /// The total number of registered callbacks.
  int get length => _voidCallbacks.length + _playbackCallbacks.length;

  /// Dispatches a `display_events` channel [event] to the matching callback.
  void dispatch(Map<Object?, Object?> event) {
    final id = event['callbackId'] as String?;
    if (id == null) return;
    final playback = _playbackCallbacks[id];
    if (playback != null) {
      playback(DisplayPlaybackEvent.fromMap(event));
      return;
    }
    _voidCallbacks[id]?.call();
  }
}

/// Base class for every node in a display view tree sent to the glasses with
/// `MetaWearablesDat.sendDisplayView`.
///
/// A tree is built declaratively, e.g.:
///
/// ```dart
/// FlexBox(
///   direction: DisplayDirection.column,
///   spacing: 12,
///   children: [
///     DisplayText('Hello', style: DisplayTextStyle.heading),
///     DisplayButton(label: 'OK', onClick: () => print('tapped')),
///   ],
/// )
/// ```
sealed class DisplayNode {
  /// Const base constructor.
  const DisplayNode();

  /// Serializes this node (and its subtree) to a platform-channel map.
  ///
  /// When [callbacks] is provided, any attached tap / click / playback
  /// handlers are registered into it and the resulting ids are embedded in the
  /// returned map. When `null`, callbacks are omitted (useful for inspection
  /// and tests).
  Map<String, Object?> toJson([DisplayCallbackTable? callbacks]);
}

/// The root of a display view tree. Any [DisplayNode] may be a root, but in
/// practice this is a [FlexBox] or a [VideoPlayer].
typedef DisplayView = DisplayNode;

/// A flexbox container that arranges its [children] along a [direction].
///
/// Mirrors Meta's `FlexBox` (iOS) / `flexBox { }` (Android) builder, including
/// the `padding`, `background`, `flexGrow` and `onTap` modifiers.
class FlexBox extends DisplayNode {
  /// Creates a [FlexBox].
  const FlexBox({
    this.children = const <DisplayNode>[],
    this.direction = DisplayDirection.column,
    this.spacing = 0,
    this.padding,
    this.background,
    this.alignment,
    this.crossAlignment,
    this.cornerRadius,
    this.wrap,
    this.flexGrow,
    this.onTap,
  });

  /// The child nodes laid out inside this container.
  final List<DisplayNode> children;

  /// The axis children are laid out along.
  final DisplayDirection direction;

  /// The gap between adjacent children, in logical pixels.
  final int spacing;

  /// Optional uniform inner padding, in logical pixels.
  final int? padding;

  /// Optional background preset.
  final FlexBoxBackground? background;

  /// Optional main-axis alignment.
  final DisplayAlignment? alignment;

  /// Optional cross-axis alignment.
  final DisplayAlignment? crossAlignment;

  /// Optional corner-radius preset.
  final DisplayCornerRadius? cornerRadius;

  /// Whether children may wrap onto multiple lines.
  final bool? wrap;

  /// Optional flex-grow factor relative to sibling [FlexBox]es.
  final double? flexGrow;

  /// Optional tap handler for the whole container.
  final void Function()? onTap;

  @override
  Map<String, Object?> toJson([DisplayCallbackTable? callbacks]) {
    return <String, Object?>{
      'type': 'flexBox',
      'direction': direction.wireName,
      'spacing': spacing,
      if (padding != null) 'padding': padding,
      if (background != null) 'background': background!.wireName,
      if (alignment != null) 'alignment': alignment!.wireName,
      if (crossAlignment != null) 'crossAlignment': crossAlignment!.wireName,
      if (cornerRadius != null) 'cornerRadius': cornerRadius!.wireName,
      if (wrap != null) 'wrap': wrap,
      if (flexGrow != null) 'flexGrow': flexGrow,
      if (callbacks?.registerTap(onTap) case final String id) 'onTapId': id,
      'children': children.map((child) => child.toJson(callbacks)).toList(growable: false),
    };
  }
}

/// A run of text rendered on the glasses display.
class DisplayText extends DisplayNode {
  /// Creates a [DisplayText].
  const DisplayText(this.text, {this.style, this.color});

  /// The text to render.
  final String text;

  /// Optional typographic style.
  final DisplayTextStyle? style;

  /// Optional color role.
  final DisplayTextColor? color;

  @override
  Map<String, Object?> toJson([DisplayCallbackTable? callbacks]) {
    return <String, Object?>{
      'type': 'text',
      'text': text,
      if (style != null) 'style': style!.wireName,
      if (color != null) 'color': color!.wireName,
    };
  }
}

/// A remote image rendered on the glasses display.
class DisplayImage extends DisplayNode {
  /// Creates a [DisplayImage].
  const DisplayImage(this.uri, {this.sizePreset, this.cornerRadius});

  /// The image URL.
  final String uri;

  /// Optional sizing preset.
  final DisplayImageSize? sizePreset;

  /// Optional corner-radius preset.
  final DisplayCornerRadius? cornerRadius;

  @override
  Map<String, Object?> toJson([DisplayCallbackTable? callbacks]) {
    return <String, Object?>{
      'type': 'image',
      'uri': uri,
      if (sizePreset != null) 'sizePreset': sizePreset!.wireName,
      if (cornerRadius != null) 'cornerRadius': cornerRadius!.wireName,
    };
  }
}

/// A tappable button rendered on the glasses display.
class DisplayButton extends DisplayNode {
  /// Creates a [DisplayButton].
  const DisplayButton({
    required this.label,
    this.style,
    this.iconName,
    this.onClick,
  });

  /// The button's text label.
  final String label;

  /// Optional visual style.
  final DisplayButtonStyle? style;

  /// Optional leading icon.
  final DisplayIconName? iconName;

  /// Optional click handler.
  final void Function()? onClick;

  @override
  Map<String, Object?> toJson([DisplayCallbackTable? callbacks]) {
    return <String, Object?>{
      'type': 'button',
      'label': label,
      if (style != null) 'style': style!.wireName,
      if (iconName != null) 'iconName': iconName!.wireName,
      if (callbacks?.registerTap(onClick) case final String id) 'onClickId': id,
    };
  }
}

/// A standalone built-in glyph rendered on the glasses display.
class DisplayIcon extends DisplayNode {
  /// Creates a [DisplayIcon].
  const DisplayIcon(this.name);

  /// The glyph to render.
  final DisplayIconName name;

  @override
  Map<String, Object?> toJson([DisplayCallbackTable? callbacks]) {
    return <String, Object?>{
      'type': 'icon',
      'iconName': name.wireName,
    };
  }
}

/// A video player rendered on the glasses display.
///
/// Playback transitions are delivered to [onPlaybackEvent] (e.g. when the
/// video ends), mirroring Meta's `VideoPlayer.state` (Android) /
/// `Display.onPlaybackEvent` (iOS).
class VideoPlayer extends DisplayNode {
  /// Creates a [VideoPlayer] sourced from a remote [uri].
  const VideoPlayer(
    this.uri, {
    this.codec = DisplayVideoCodec.mp4,
    this.onPlaybackEvent,
  });

  /// The video URL.
  final String uri;

  /// The container codec hint.
  final DisplayVideoCodec codec;

  /// Optional playback-event handler.
  final void Function(DisplayPlaybackEvent)? onPlaybackEvent;

  @override
  Map<String, Object?> toJson([DisplayCallbackTable? callbacks]) {
    return <String, Object?>{
      'type': 'videoPlayer',
      'uri': uri,
      'codec': codec.wireName,
      if (callbacks?.registerPlayback(onPlaybackEvent) case final String id) 'onPlaybackEventId': id,
    };
  }
}
