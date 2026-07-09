/// The kind of a [DisplayPlaybackEvent] emitted by a `VideoPlayer` rendered
/// on the glasses display.
///
/// Mirrors the playback states reported by Meta's DAT SDKs
/// (`VideoPlayerState` on Android, the `onPlaybackEvent` callback on iOS).
enum DisplayPlaybackEventType {
  /// Playback has begun (or resumed).
  playing('playing'),

  /// Playback has been paused.
  paused('paused'),

  /// Playback reached the end of the media.
  ended('ended'),

  /// Playback was stopped before completing.
  stopped('stopped'),

  /// The player reported an error.
  error('error'),

  /// An event the plugin did not recognise.
  unknown('unknown');

  const DisplayPlaybackEventType(this.wireName);

  /// The string used on the platform channel.
  final String wireName;

  /// Maps a platform-channel string to a [DisplayPlaybackEventType].
  static DisplayPlaybackEventType fromWire(String? wire) {
    for (final value in DisplayPlaybackEventType.values) {
      if (value.wireName == wire) return value;
    }
    return DisplayPlaybackEventType.unknown;
  }
}

/// A playback event delivered to a `VideoPlayer`'s `onPlaybackEvent`
/// callback while it is rendered on the glasses display.
class DisplayPlaybackEvent {
  /// Creates a [DisplayPlaybackEvent].
  const DisplayPlaybackEvent({required this.type});

  /// Builds a [DisplayPlaybackEvent] from a platform-channel map.
  factory DisplayPlaybackEvent.fromMap(Map<Object?, Object?> map) {
    return DisplayPlaybackEvent(
      type: DisplayPlaybackEventType.fromWire(map['event'] as String?),
    );
  }

  /// The kind of playback transition this event represents.
  final DisplayPlaybackEventType type;

  @override
  String toString() => 'DisplayPlaybackEvent(type: ${type.wireName})';
}
