import 'package:just_audio/just_audio.dart';

import 'package:omi/utils/logger.dart';

/// Short UI feedback sounds.
///
/// Deliberately fire-and-forget: a UI sound is a garnish, and no user-facing
/// action may fail or stall because audio did not play. Every path swallows its
/// error and logs, and nothing here is awaited by a caller that matters.
///
/// One player is kept warm per sound so a tap does not pay asset-load latency —
/// the chime has to land with the tap or it reads as lag rather than feedback.
class UiSounds {
  UiSounds._();

  static final UiSounds instance = UiSounds._();

  static const String _taskCompleteAsset = 'assets/sounds/task_complete.wav';

  AudioPlayer? _taskComplete;
  bool _taskCompleteFailed = false;

  /// Preloads the players. Safe to call more than once; safe never to call at
  /// all, in which case the first play loads on demand.
  Future<void> warmUp() async {
    await _taskCompletePlayer();
  }

  Future<AudioPlayer?> _taskCompletePlayer() async {
    if (_taskCompleteFailed) return null;
    if (_taskComplete != null) return _taskComplete;
    try {
      final player = AudioPlayer();
      await player.setAsset(_taskCompleteAsset);
      _taskComplete = player;
      return player;
    } catch (e, s) {
      // One failure is enough — don't retry the asset on every checkbox tap.
      _taskCompleteFailed = true;
      Logger.instance.talker.handle(e, s, 'UiSounds: failed to load $_taskCompleteAsset');
      return null;
    }
  }

  /// The "cha-ching" played when a task is checked off.
  ///
  /// Never played when un-checking — the sound marks an accomplishment, and
  /// hearing it on undo would be actively confusing.
  Future<void> playTaskComplete() async {
    try {
      final player = await _taskCompletePlayer();
      if (player == null) return;
      // Rewind rather than replay from wherever the last tap left it, so
      // checking several tasks quickly retriggers cleanly.
      await player.seek(Duration.zero);
      // Not awaited: play() completes when playback *finishes*, and the caller
      // is mid-animation.
      player.play();
    } catch (e, s) {
      Logger.instance.talker.handle(e, s, 'UiSounds: task complete playback failed');
    }
  }

  Future<void> dispose() async {
    await _taskComplete?.dispose();
    _taskComplete = null;
  }
}
