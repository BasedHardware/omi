import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/schema/transcript_segment.dart';

/// Performs a wall-clock seek on the detail player. [strict] selects the
/// no-gap-snap mapping (a transcript line tap); a scrub or reader reposition
/// snaps into the nearest captured span. [play] starts playback after the seek.
typedef ConversationPlaybackSeekHandler = Future<void> Function(double wallSeconds,
    {required bool play, required bool strict});

/// Playback state shared by the detail page's audio bar and its transcript.
///
/// The page owns and disposes this; the bottom bar attaches its seek handler
/// and reports player positions, and the transcript reads the highlight and
/// follow intent. Positions are wall-clock seconds — the same timeline the
/// transcript segments use — so silence and collapsed gaps behave the same on
/// both sides.
class ConversationPlaybackController extends ChangeNotifier {
  ConversationPlaybackController({List<TranscriptSegment> segments = const []}) : _segments = List.of(segments);

  List<TranscriptSegment> _segments;
  String? _currentSegmentId;
  String? _followTargetSegmentId;
  bool _isPlaying = false;
  bool _isLoaded = false;
  bool _isFollowing = true;
  int _followRequest = 0;
  int _intentGeneration = 0;

  /// Fine-grained playhead on the wall timeline; ticks on every position
  /// report without rebuilding the transcript.
  final ValueNotifier<double> wallPosition = ValueNotifier(0);

  double? _pendingWall;
  bool _pendingStrict = false;
  double? _pausedWall;
  bool _mapped = true;
  ConversationPlaybackSeekHandler? _seekHandler;

  bool _isDisposed = false;

  /// The segment containing the playhead on [start, end), or null through
  /// silence — never the nearest segment across a gap.
  String? get currentSegmentId => _currentSegmentId;

  /// Where the transcript should scroll while following: the containing
  /// segment, or the next one when the playhead sits in silence (the last one
  /// when it runs past the final segment).
  String? get followTargetSegmentId => _followTargetSegmentId;

  bool get isPlaying => _isPlaying;
  bool get isLoaded => _isLoaded;
  bool get isFollowing => _isFollowing;

  /// Bumped on every explicit follow trigger (line tap, scrub, back-to-current)
  /// so the transcript re-scrolls even when the target id did not change.
  int get followRequest => _followRequest;

  /// Monotonic intent counter: the bar compares it around awaited init/seek so
  /// only the latest user gesture lands.
  int get intentGeneration => _intentGeneration;

  bool get hasPending => _pendingWall != null;
  bool get pendingStrict => _pendingStrict;
  double? get pendingWallSeconds => _pendingWall;

  /// The wall point the next Play should start from. Right after a pause the
  /// paused position stands until the user scrolls again.
  double? get resumeWall => _pausedWall ?? _pendingWall;

  /// Consumes the pending point after the bar has applied it.
  void clearPending() {
    _pendingWall = null;
    _pendingStrict = false;
  }

  void updateSegments(List<TranscriptSegment> segments) {
    _segments = List.of(segments);
    // Deliberately no synchronous notifyListeners: callers invoke this from a
    // build. If the target ids move, the next reportPlayback picks it up.
    // While the player has no wall mapping, no line may be claimed current —
    // a rebuild must not re-mark one.
    if (_mapped) {
      _recomputeTargets();
    } else {
      _clearTargets();
    }
  }

  void attachSeekHandler(ConversationPlaybackSeekHandler handler) {
    _seekHandler = handler;
  }

  void detachSeekHandler(ConversationPlaybackSeekHandler handler) {
    if (identical(_seekHandler, handler)) _seekHandler = null;
  }

  /// Position/state report from the player, already mapped onto the wall
  /// timeline. Notifies only when the highlight, playing or loaded state
  /// changed — position ticks go through [wallPosition] alone — and only once
  /// every field is already updated. When the player has no wall mapping
  /// (parts without timestamps), [mapped] false drops the highlight targets:
  /// audio can still play, but no transcript line can be claimed as current.
  void reportPlayback({required double wallSeconds, required bool playing, required bool loaded, bool mapped = true}) {
    if (_isDisposed) return;
    wallPosition.value = wallSeconds;
    _mapped = mapped;
    var changed = mapped ? _recomputeTargets() : _clearTargets();
    if (loaded != _isLoaded) {
      _isLoaded = loaded;
      changed = true;
    }
    if (playing != _isPlaying) {
      if (_isPlaying && !playing) _pausedWall = wallSeconds;
      _isPlaying = playing;
      if (playing) _pausedWall = null;
      changed = true;
    }
    if (changed) notifyListeners();
  }

  /// The player widget was torn down (dispose, conversation change, retry):
  /// playback state no longer exists, but the reader's point survives. The
  /// current wall becomes the resume point only when no newer pending intent
  /// or paused point already does. [notify] is off during widget disposal —
  /// listeners may already be gone.
  void playerDetached({bool notify = true}) {
    if (_isDisposed) return;
    if (_pendingWall == null && _pausedWall == null) _pausedWall = wallPosition.value;
    final changed = _isPlaying || _isLoaded;
    _isPlaying = false;
    _isLoaded = false;
    if (notify && changed) notifyListeners();
  }

  /// A reader gesture owns the scroll: playback keeps going, following stops.
  void suspendFollowing() {
    if (_isDisposed || !_isFollowing) return;
    _isFollowing = false;
    notifyListeners();
  }

  /// Scroll back to the current line and keep following it.
  void backToCurrent() {
    if (_isDisposed) return;
    _isFollowing = true;
    _followRequest++;
    _intentGeneration++;
    notifyListeners();
  }

  /// The user dragged or flung the transcript to [segment].
  ///
  /// While playing this only suspends following — the audio keeps its place.
  /// Paused or idle it becomes the new read point: the pending wall moves to
  /// the segment's start, the waveform playhead follows, and an already-loaded
  /// player seeks (without starting playback).
  void readerMovedTo(TranscriptSegment segment) {
    if (_isDisposed) return;
    _intentGeneration++;
    if (_isPlaying) {
      suspendFollowing();
      return;
    }
    _pausedWall = null;
    _pendingWall = segment.start;
    _pendingStrict = false;
    wallPosition.value = segment.start;
    _recomputeTargets();
    notifyListeners();
    // An unloaded reader scroll moves the read point without loading audio;
    // a loaded one repositions the paused player without starting playback.
    if (_isLoaded) unawaited(_invokeSeek(segment.start, play: false, strict: false));
  }

  /// An explicit playback seek: a transcript line tap ([strict], [play]), a
  /// waveform scrub, or a programmatic jump. Always resumes following and
  /// answers the gesture immediately: the wall playhead and targets move even
  /// before the player exists. When the player is not loaded yet the intent is
  /// also recorded as pending so a later Play applies it; [play] forwards to
  /// the seek handler anyway, which initializes the player then seeks.
  void seek(double wallSeconds, {bool play = false, bool strict = false}) {
    if (_isDisposed) return;
    _intentGeneration++;
    _pausedWall = null;
    // Pending is kept on every explicit seek — a stale in-flight seek must
    // never drop the newest intent; the bar clears it only after applying it.
    _pendingWall = wallSeconds;
    _pendingStrict = strict;
    wallPosition.value = wallSeconds;
    _recomputeTargets();
    _isFollowing = true;
    _followRequest++;
    notifyListeners();
    if (_isLoaded || play) {
      unawaited(_invokeSeek(wallSeconds, play: play, strict: strict));
    }
  }

  Future<void> _invokeSeek(double wallSeconds, {required bool play, required bool strict}) =>
      _seekHandler?.call(wallSeconds, play: play, strict: strict) ?? Future<void>.value();

  bool _clearTargets() {
    if (_currentSegmentId == null && _followTargetSegmentId == null) return false;
    _currentSegmentId = null;
    _followTargetSegmentId = null;
    return true;
  }

  bool _recomputeTargets() {
    final wall = wallPosition.value;
    String? current;
    String? follow;
    for (final segment in _segments) {
      if (wall >= segment.start && wall < segment.end) {
        current = segment.id;
        break;
      }
    }
    if (current != null) {
      follow = current;
    } else {
      for (final segment in _segments) {
        if (segment.start > wall) {
          follow = segment.id;
          break;
        }
      }
      follow ??= _segments.isEmpty ? null : _segments.last.id;
    }
    if (current != _currentSegmentId || follow != _followTargetSegmentId) {
      _currentSegmentId = current;
      _followTargetSegmentId = follow;
      return true;
    }
    return false;
  }

  @override
  void dispose() {
    _isDisposed = true;
    wallPosition.dispose();
    super.dispose();
  }
}
