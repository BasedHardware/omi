import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';

import '../support/typed_conversation_screen.dart';

void main() {
  setUp(() => VisibilityDetectorController.instance.updateInterval = Duration.zero);
  for (final targets in <List<String>>[
    [],
    ['a'],
    ['a', 'b']
  ]) {
    for (final loading in [false, true]) {
      testWidgets('Home has no pending row for server targets=$targets, loading=$loading', (tester) async {
        tester.view.physicalSize = const Size(390, 1400);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        final store = PendingWorkStore(
          loadPending: () async => ApiSuccess(PendingWorkSnapshot(enabled: true, attentionUnseenCount: 0, items: [
            PendingWorkItem(
                id: 'sync:job',
                kind: 'sync_job',
                state: 'transcribing',
                conversationIds: targets,
                durationSeconds: 720),
          ])),
          loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled),
        );
        final provider = ConversationProvider(isSignedIn: () => false)..isLoadingConversations = loading;
        addTearDown(store.dispose);
        addTearDown(provider.dispose);
        final screen = await buildTypedConversationScreen(provider, pendingWork: store);
        await store.refresh();
        provider.processingConversations = [
          ServerConversation(
              id: 'processing',
              createdAt: DateTime.now(),
              structured: Structured('', ''),
              status: ConversationStatus.processing),
        ];
        await tester.pumpWidget(screen);
        await tester.pump(const Duration(milliseconds: 300));
        expect(find.byKey(const Key('home_pending_row')), findsNothing);
        expect(find.text('Conversations on the way'), findsNothing);
        expect(find.text('Catching up on earlier audio'), findsNothing);
        provider.removeProcessingConversation('processing');
        await provider.addConversation(ServerConversation(
            id: 'done',
            createdAt: DateTime.now(),
            structured: Structured('Finished recording', 'Overview'),
            status: ConversationStatus.completed));
        provider.setLoadingConversations(false);
        await tester.pump();
        expect(find.byKey(const Key('home_pending_row')), findsNothing);
        expect(find.byType(ConversationListItem), findsOneWidget);
        await tester.pumpWidget(const SizedBox.shrink());
      });
    }
  }
}
