import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';

import '../../support/typed_conversation_screen.dart';

/// Home has no capture banner at all. Acute link failures speak on the live page (a status
/// line under the header) and light the Activity bell's warning dot; slow-burn problems
/// (storage at risk, upload silence) are Needs attention rows in Activity (see
/// needs_attention_capture_test.dart).
void main() {
  setUp(() => VisibilityDetectorController.instance.updateInterval = Duration.zero);

  CaptureWedgeMonitor swapInMonitor() {
    final previous = CaptureWedgeMonitor.instance;
    final monitor = CaptureWedgeMonitor(
      featureGate: () async => true,
      track: (_, __) {},
      bleRetry: (_) async {},
      transferRetry: () async {},
      appBuild: () => '1',
      platform: () => 'ios',
    );
    CaptureWedgeMonitor.instance = monitor;
    addTearDown(() {
      CaptureWedgeMonitor.instance = previous;
      monitor.dispose();
    });
    return monitor;
  }

  Future<ConversationProvider> seedConversations() async {
    final now = DateTime.now();
    final items = [
      ServerConversation(
        id: 'h1',
        createdAt: now.subtract(const Duration(hours: 2)),
        structured: Structured('Capture banner check', 'Overview', emoji: '🔧', category: 'work'),
        status: ConversationStatus.completed,
      ),
    ];
    final conversations = ConversationProvider(
      conversationListFetcher: () async => (items: items, ok: true),
      isSignedIn: () => true,
    )
      ..conversations = items
      ..groupConversationsByDate();
    addTearDown(conversations.dispose);
    return conversations;
  }

  Future<void> pumpHome(WidgetTester tester, ConversationProvider conversations) async {
    await tester.pumpWidget(await buildTypedConversationScreen(conversations));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 250));
  }

  testWidgets('Home shows no banner for an acute zero-byte episode', (tester) async {
    tester.view.physicalSize = const Size(800, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final monitor = swapInMonitor();
    final conversations = await seedConversations();
    // Three zero-byte capture sessions: the acute link failure that used to keep a
    // Home banner. It now reaches a Home reader through the bell's dot instead.
    for (var i = 0; i < 3; i++) {
      final handle = monitor.onCaptureSessionConnected(deviceId: 'dev-a', source: 'omi');
      monitor.onCaptureSessionEnded(handle, binaryBytesSent: 0);
    }

    await pumpHome(tester, conversations);

    expect(tester.takeException(), isNull);
    expect(monitor.acuteEpisode, isNotNull, reason: 'the seeded episode is acute and visible');
    expect(find.byKey(const Key('capture_recovery_status')), findsNothing);
    expect(find.text('Omi isn\'t sending audio'), findsNothing,
        reason: 'Home carries no capture banner; the bell dot is the signal');
    expect(monitor.hasUnseenCaptureAttention.value, isTrue, reason: 'the bell warns instead');
    expect(find.text('Capture banner check'), findsOneWidget, reason: 'the page itself still renders');
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('Home shows no banner for the slow-burn storage episode', (tester) async {
    tester.view.physicalSize = const Size(800, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final monitor = swapInMonitor();
    final conversations = await seedConversations();
    // Disk admission failures: the slow-burn trigger that moved to Activity.
    monitor.observeStorageAtRisk(
      engagedAt: DateTime.now().subtract(const Duration(minutes: 30)),
      blockedCount: 3,
      retainedCount: 720,
      reason: 'disk_reserve',
    );

    await pumpHome(tester, conversations);

    expect(tester.takeException(), isNull);
    expect(find.byKey(const Key('capture_recovery_status')), findsNothing);
    expect(find.text('Phone storage full'), findsNothing,
        reason: 'storage at risk is slow-burn and lives in Activity, not on Home');
    expect(find.text('Capture banner check'), findsOneWidget, reason: 'the page itself still renders');
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
