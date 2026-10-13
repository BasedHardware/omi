import 'dart:async';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/capture_provider.dart';
import 'first_capture_controller.dart';

class PhoneFirstCaptureIO implements FirstCaptureIO {
  PhoneFirstCaptureIO(this.capture,
      {Future<ServerConversation?> Function(String)? loadConversation, Future<void> Function(Duration)? wait})
      : loadConversation = loadConversation ?? getConversationById,
        wait = wait ?? Future<void>.delayed;
  final CaptureProvider capture;
  bool _started = false;
  String? _recordingId;
  String _lastTranscript = '';
  final Future<ServerConversation?> Function(String) loadConversation;
  final Future<void> Function(Duration) wait;
  @override
  String get transcript {
    if (capture.activeRecordingId == _recordingId) {
      final live = capture.segments.map((s) => s.text).join(' ');
      if (live.isNotEmpty) _lastTranscript = live;
    }
    return _lastTranscript;
  }

  @override
  Future<void> start() async {
    if (capture.liveCaptureSource == 'phone') throw StateError('phone capture already active');
    _lastTranscript = '';
    await capture.streamRecording();
    _started = true;
    _recordingId = capture.activeRecordingId;
    if (capture.isPhoneMicBatchRecording) {
      await cancel();
      throw StateError('live capture requires connectivity');
    }
  }

  @override
  Future<ServerConversation?> finish({bool Function()? isCurrent}) async {
    _started = false;
    transcript;
    final response = await capture.finishCaptureWithResult();
    if (isCurrent?.call() == false) return null;
    var conversation = response?.conversation;
    if (conversation == null) return null;
    if (conversation.transcriptSegments.isNotEmpty) {
      _lastTranscript = conversation.transcriptSegments.map((s) => s.text).join(' ');
    }
    // Process Now can return a still-processing row. Poll only its confirmed id,
    // using the existing conversation API, never the newest item in the list.
    for (var i = 0; i < 30; i++) {
      if (isCurrent?.call() == false) return null;
      if (conversation!.status == ConversationStatus.completed) {
        if (conversation.transcriptSegments.isNotEmpty) {
          _lastTranscript = conversation.transcriptSegments.map((s) => s.text).join(' ');
        }
        return conversation;
      }
      if (conversation.status == ConversationStatus.failed) throw StateError('processing failed');
      await wait(const Duration(seconds: 2));
      if (isCurrent?.call() == false) return null;
      conversation = await loadConversation(conversation.id) ?? conversation;
    }
    if (isCurrent?.call() == false) return null;
    throw TimeoutException('conversation still processing');
  }

  @override
  Future<void> cancel() async {
    if (!_started) return;
    _started = false;
    if (capture.liveCaptureSource == 'phone' && capture.activeRecordingId == _recordingId) {
      await capture.stopStreamRecording();
    }
  }
}
