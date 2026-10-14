import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/onboarding/first_capture_io.dart';

class _Capture implements CaptureProvider {
  String? source;
  int stops = 0;
  final pending = Completer<CreateConversationResponse?>();
  @override
  String? get liveCaptureSource => source;
  @override
  String? get activeRecordingId => 'owned';
  @override
  bool get isPhoneMicBatchRecording => false;
  @override
  List<TranscriptSegment> get segments => [];
  @override
  Future<void> streamRecording({bool resumeCapture = true}) async {
    source = 'phone';
  }

  @override
  Future<CreateConversationResponse?> finishCaptureWithResult() => pending.future;
  @override
  Future<bool> stopStreamRecording({String reason = 'user_stopped', bool resumeHandedOffPendant = true}) async {
    stops++;
    return true;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnsupportedError(invocation.memberName.toString());
}

void main() {
  test('terminal discarded failure reaches the guided outcome classifier', () async {
    final capture = _Capture();
    final io = PhoneFirstCaptureIO(capture);
    await io.start();
    final discarded = ServerConversation(
        id: 'discarded',
        createdAt: DateTime(2026),
        structured: Structured('', ''),
        status: ConversationStatus.failed,
        discarded: true);
    capture.pending.complete(CreateConversationResponse(messages: [], conversation: discarded));
    expect(await io.finish(), same(discarded));
  });

  test('leaving while Finish awaits never cancels; superseded attempt performs no more polling', () async {
    final capture = _Capture();
    final sleep = Completer<void>();
    var current = true, loads = 0;
    final io = PhoneFirstCaptureIO(capture,
        wait: (_) => sleep.future,
        loadConversation: (_) async {
          loads++;
          return null;
        });
    await io.start();
    final finishing = io.finish(isCurrent: () => current);
    await io.cancel();
    expect(capture.stops, 0);
    capture.pending.complete(CreateConversationResponse(
        messages: [],
        conversation: ServerConversation(
            id: 'confirmed',
            createdAt: DateTime(2026),
            structured: Structured('', ''),
            status: ConversationStatus.processing)));
    await Future<void>.delayed(Duration.zero);
    current = false;
    sleep.complete();
    expect(await finishing, isNull);
    expect(loads, 0);
  });
}
