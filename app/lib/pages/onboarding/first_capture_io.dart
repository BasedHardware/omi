import 'dart:async';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/capture_provider.dart';
import 'first_capture_controller.dart';

class PhoneFirstCaptureIO implements FirstCaptureIO {
  PhoneFirstCaptureIO(this.capture);
  final CaptureProvider capture;
  bool _started = false;
  String? _recordingId;
  @override
  String get transcript => capture.segments.map((s) => s.text).join(' ');

  @override
  Future<void> start() async {
    if (capture.liveCaptureSource == 'phone') throw StateError('phone capture already active');
    await capture.streamRecording();
    _started = true;
    _recordingId = capture.activeRecordingId;
    if (capture.isPhoneMicBatchRecording) {
      await cancel();
      throw StateError('live capture requires connectivity');
    }
  }

  @override
  Future<ServerConversation?> finish() async {
    final response = await capture.finishCaptureWithResult();
    _started = false;
    var conversation = response?.conversation;
    if (conversation == null) return null;
    // Process Now can return a still-processing row. Poll only its confirmed id,
    // using the existing conversation API, never the newest item in the list.
    for (var i = 0; i < 30; i++) {
      if (conversation!.status == ConversationStatus.completed) return conversation;
      if (conversation.status == ConversationStatus.failed) throw StateError('processing failed');
      await Future<void>.delayed(const Duration(seconds: 2));
      conversation = await getConversationById(conversation.id) ?? conversation;
    }
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
