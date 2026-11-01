import 'dart:io';

import 'package:flutter/services.dart';
import 'package:path/path.dart' as p;

import 'package:omi/utils/logger.dart';

/// Video file extensions chat treats as clips (sampled, never sent whole when avoidable).
const chatVideoExtensions = {'.mp4', '.mov', '.m4v', '.3gp', '.webm', '.mkv'};

bool isChatVideo(String path) => chatVideoExtensions.contains(p.extension(path).toLowerCase());

/// Frames and audio a native sampler wrote to a temp directory for `POST /v2/files/video`.
class SampledChatVideo {
  SampledChatVideo({
    required this.frames,
    required this.times,
    required this.duration,
    required this.audio,
    required this.directory,
  });

  final List<File> frames;
  final List<double> times;
  final double duration;
  final File? audio;
  final Directory directory;

  Future<void> dispose() async {
    try {
      await directory.delete(recursive: true);
    } catch (_) {}
  }
}

/// `com.omi/chat_video`: AVFoundation on iOS, MediaMetadataRetriever + MediaMuxer on Android.
///
/// Same candidate set as the backend and desktop samplers (≤48 frames, ≤4 per second,
/// 384 px). Returns null when the platform has no sampler or the clip can't be read; the
/// caller then uploads the clip itself and the server samples it.
class ChatVideoSampler {
  static const _channel = MethodChannel('com.omi/chat_video');

  static Future<void> _deleteQuietly(String? path) async {
    if (path == null) return;
    try {
      await Directory(path).delete(recursive: true);
    } catch (_) {}
  }

  static Future<SampledChatVideo?> sample(File video) async {
    if (!Platform.isIOS && !Platform.isAndroid) return null;
    try {
      final result = await _channel.invokeMapMethod<String, dynamic>('sample', {'path': video.path});
      if (result == null || result['audio_unsupported'] == true) return null;
      final directory = result['directory'];
      try {
        final frames = (result['frames'] as List).cast<String>().map(File.new).toList();
        final times = (result['times'] as List).map((t) => (t as num).toDouble()).toList();
        final audio = result['audio'] as String?;
        if (frames.isEmpty || frames.length != times.length) throw const FormatException('frames/times');
        return SampledChatVideo(
          frames: frames,
          times: times,
          duration: (result['duration'] as num).toDouble(),
          audio: audio == null ? null : File(audio),
          directory: Directory(directory as String),
        );
      } catch (_) {
        // A malformed native result: drop its temp files and upload the clip instead.
        await _deleteQuietly(directory is String ? directory : null);
        return null;
      }
    } on MissingPluginException {
      return null;
    } on PlatformException catch (e) {
      Logger.debug('ChatVideoSampler: ${e.code}');
      return null;
    }
  }
}
