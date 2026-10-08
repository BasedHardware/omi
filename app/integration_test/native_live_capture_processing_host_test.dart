import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/pages/processing_conversations/page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

import 'journeys/support/hermetic_boot.dart';
import 'support/native_host_harness.dart';

class _NoopBle implements CaptureBleListeners {
  @override
  void addBatchRecordingFinalizedListener(void Function(String) callback) {}
  @override
  void removeBatchRecordingFinalizedListener(void Function(String) callback) {}
}

class _InertWal implements IWalService {
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

/// Seeded live capture with no microphone, socket or upload behind it; Finish is only counted.
class _InertCapture extends CaptureProvider {
  _InertCapture()
      : super(
          walService: _InertWal(),
          connectivity: CaptureConnectivityBoundary(
              initiallyConnected: true, changes: const Stream.empty(), isConnected: () => true),
          bleListeners: _NoopBle(),
          inProgressConversationLoader: () async {},
          localSegmentStore: LocalSegmentStore.disabled(),
        );

  int finishes = 0;

  @override
  String? get liveCaptureSource => 'phone';
  @override
  bool get pendantCaptureVerified => true;
  @override
  Future<void> finishCapture() async => finishes++;
}

TranscriptSegment _segment(String id, String text, double start) => TranscriptSegment(
    id: id,
    text: text,
    speaker: 'SPEAKER_01',
    isUser: false,
    personId: null,
    start: start,
    end: start + 2,
    translations: []);

/// Run on Simulator with OMI_APP_PROFILE=local_dev and OMI_IOS_SWIFTUI=true.
void main() => runNativeHostSuite((checkNativeHost) {
      testWidgets('native live capture is contained natively and Finish reaches the capture owner', (tester) async {
        await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
        addTearDown(JourneyHermeticBoot.stop);
        final capture = _InertCapture()
          ..segments = [_segment('a', 'We should ship the native capture page.', 0), _segment('b', 'Agreed.', 3)];
        addTearDown(capture.dispose);
        await tester.pumpWidget(nativeHostApp(const Scaffold(body: Center(child: Text('home'))),
            providers: [ChangeNotifierProvider<CaptureProvider>.value(value: capture)]));
        unawaited(Navigator.of(tester.element(find.text('home')))
            .push(MaterialPageRoute<void>(builder: (_) => const ConversationCapturingPage())));
        await tester.pump(const Duration(milliseconds: 500));
        await checkNativeHost(tester, 'native-live-capture-processing-capture-dark');
        expect(nativeProjectedRow(tester, 'capture_segment:1').title, 'Agreed.');
        await nativeProjectedRow(tester, 'capture_finish').action!(null);
        await tester.pump(const Duration(seconds: 1));
        expect(capture.finishes, 1);
        expect(find.byType(ConversationCapturingPage), findsNothing);
        expect(tester.takeException(), isNull);
      });

      testWidgets('native processing page renders the captured transcript', (tester) async {
        await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
        addTearDown(JourneyHermeticBoot.stop);
        final conversation = ServerConversation(
            id: 'native-processing',
            createdAt: DateTime.now(),
            finishedAt: DateTime.now(),
            status: ConversationStatus.processing,
            structured: Structured('', ''),
            transcriptSegments: [_segment('a', 'Words captured before processing.', 0)]);
        await tester.pumpWidget(nativeHostApp(ProcessingConversationPage(conversation: conversation)));
        await checkNativeHost(tester, 'native-live-capture-processing-processing-dark');
        expect(nativeProjectedRow(tester, 'processing_segment:0').title, 'Words captured before processing.');
        expect(tester.takeException(), isNull);
      });
    });
