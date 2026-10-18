import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';

import '../../support/typed_conversation_screen.dart';

/// The Home banner is gone: slow-burn capture problems live in Activity's Needs attention
/// section (see needs_attention_capture_test.dart), and the live amber pill plus the capturing
/// page's single banner carry anything acute. Home must stay banner-free even while the monitor
/// holds an episode that would have shown one.
void main() {
  setUp(() => VisibilityDetectorController.instance.updateInterval = Duration.zero);

  testWidgets('Home renders no capture recovery banner, even with a visible wedge episode', (tester) async {
    tester.view.physicalSize = const Size(800, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

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
    // Disk admission failures: the trigger whose banner used to sit on Home.
    monitor.observeStorageAtRisk(
      engagedAt: DateTime.now().subtract(const Duration(minutes: 30)),
      blockedCount: 3,
      retainedCount: 720,
      reason: 'disk_reserve',
    );

    await tester.pumpWidget(await buildTypedConversationScreen(conversations));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 250));

    expect(tester.takeException(), isNull);
    expect(find.byKey(const Key('capture_recovery_banner')), findsNothing);
    expect(find.text('Capture banner check'), findsOneWidget, reason: 'the page itself still renders');
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
