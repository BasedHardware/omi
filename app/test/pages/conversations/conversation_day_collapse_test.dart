import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/processing_conversation_row.dart';
import 'package:omi/pages/conversations/widgets/recording_list_item.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:visibility_detector/visibility_detector.dart';

import '../../support/typed_conversation_screen.dart';

class _Recordings extends ChangeNotifier implements LocalRecordingsProvider {
  _Recordings(this.recordings);

  @override
  final List<LocalRecording> recordings;

  @override
  bool isPlaying(LocalRecording recording) => false;

  @override
  Future<void> refresh() async {}

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  final previousVisibilityInterval = VisibilityDetectorController.instance.updateInterval;
  setUpAll(() => VisibilityDetectorController.instance.updateInterval = Duration.zero);
  tearDownAll(() => VisibilityDetectorController.instance.updateInterval = previousVisibilityInterval);

  testWidgets('days collapse and expand without changing their conversations', (tester) async {
    tester.view.physicalSize = const Size(800, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final today = DateUtils.dateOnly(DateTime.now());
    final conversations = [
      for (final (id, title, date) in [
        ('today', 'Today conversation', today.add(const Duration(hours: 10))),
        ('yesterday', 'Yesterday conversation', today.subtract(const Duration(days: 1)).add(const Duration(hours: 10))),
      ])
        ServerConversation(
          id: id,
          createdAt: date,
          structured: Structured(title, 'Overview', emoji: '💬', category: 'work'),
          status: ConversationStatus.completed,
        ),
    ];
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: conversations, ok: true),
      isSignedIn: () => true,
    )
      ..conversations = conversations
      ..processingConversations = [
        ServerConversation(
          id: 'processing',
          createdAt: DateTime.now(),
          structured: Structured('', ''),
          status: ConversationStatus.processing,
        ),
      ]
      ..groupConversationsByDate();
    addTearDown(provider.dispose);
    final recordings = _Recordings([
      for (final state in [LocalRecordingState.pending, LocalRecordingState.failed])
        LocalRecording(
          fileName: '${state.name}.bin',
          filePath: '/tmp/${state.name}.bin',
          timerStart: today.millisecondsSinceEpoch ~/ 1000,
          codec: BleAudioCodec.opus,
          frameSize: 160,
          sizeBytes: 1024,
          seconds: 1,
          state: state,
        ),
    ]);
    addTearDown(recordings.dispose);

    await tester.pumpWidget(await buildTypedConversationScreen(provider, recordingsProvider: recordings));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 250));

    final dayKey = ValueKey('collapse_day_${today.toIso8601String()}');
    expect(find.byTooltip('Today: Collapse'), findsOneWidget);
    expect(tester.getSize(find.byKey(dayKey)).width, greaterThanOrEqualTo(48));
    expect(tester.getSize(find.byKey(dayKey)).height, greaterThanOrEqualTo(48));
    expect(find.byType(ConversationListItem), findsNWidgets(2));
    expect(find.text('Today conversation'), findsOneWidget);
    expect(find.text('Yesterday conversation'), findsOneWidget);
    expect(find.byType(ProcessingConversationRow), findsOneWidget);
    expect(find.byType(RecordingListItem), findsNWidgets(2));

    await tester.tap(find.byKey(dayKey));
    await tester.pump();
    expect(find.byTooltip('Today: Expand'), findsOneWidget);
    expect(find.text('Today conversation'), findsNothing);
    expect(find.text('Yesterday conversation'), findsOneWidget);
    expect(find.byType(ConversationListItem), findsOneWidget);
    expect(find.byType(ProcessingConversationRow), findsOneWidget);
    expect(find.byType(RecordingListItem), findsNWidgets(2));
    expect(provider.conversations.map((conversation) => conversation.id), containsAll(['today', 'yesterday']));

    await tester.tap(find.byKey(dayKey));
    await tester.pump();
    expect(find.text('Today conversation'), findsOneWidget);
    expect(find.text('Yesterday conversation'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('collapsed days load older conversations only when requested', (tester) async {
    tester.view.physicalSize = const Size(800, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final today = DateUtils.dateOnly(DateTime.now());
    ServerConversation conversation(String id, DateTime date) => ServerConversation(
          id: id,
          createdAt: date,
          structured: Structured(id, 'Overview', emoji: '💬', category: 'work'),
          status: ConversationStatus.completed,
        );
    final firstPage = List.generate(50, (index) => conversation('conversation-$index', today));
    var requests = 0;
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: firstPage, ok: true),
      isSignedIn: () => true,
    );
    provider.conversationPageFetcherOverride = () async {
      requests++;
      return (items: [conversation('older', today.subtract(const Duration(days: 1)))], ok: true, truncated: false);
    };
    addTearDown(provider.dispose);
    final screen = await buildTypedConversationScreen(provider);
    await tester.runAsync(() => provider.fetchConversations());
    await tester.pumpWidget(screen);
    await tester.pump();

    await tester.tap(find.byKey(ValueKey('collapse_day_${today.toIso8601String()}')));
    await tester.pump();
    expect(requests, 0);
    expect(find.text('show more ↓'), findsOneWidget);

    await tester.tap(find.text('show more ↓'));
    await tester.pump();
    await tester.pump();
    expect(requests, 1);
    expect(provider.conversations.any((conversation) => conversation.id == 'older'), isTrue);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
