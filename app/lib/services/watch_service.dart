import 'dart:async';
import 'package:friend_private/services/watch_manager.dart';
import 'package:friend_private/utils/errors.dart';
import 'package:friend_private/utils/logger.dart';

class WatchService {
  static final WatchService _instance = WatchService._internal();
  factory WatchService() => _instance;

  final WatchManager _manager = WatchManager();
  final _logger = Logger.instance;

  bool get isRecording => _manager.isRecording;

  WatchService._internal();

  Future<bool> checkAvailability() async {
    try {
      return await _manager.isWatchAvailable();
    } catch (e) {
      _logger.error('Error checking watch availability', e);
      return false;
    }
  }

  Future<void> startRecording() async {
    try {
      if (!await checkAvailability()) {
        throw WatchConnectionError('Watch is not available');
      }
      await _manager.startRecording();
    } catch (e) {
      _logger.error('Error starting watch recording', e);
      throw WatchRecordingError('Failed to start recording: $e');
    }
  }

  Future<void> stopRecording() async {
    try {
      await _manager.stopRecording();
    } catch (e) {
      _logger.error('Error stopping watch recording', e);
      throw WatchRecordingError('Failed to stop recording: $e');
    }
  }
}
