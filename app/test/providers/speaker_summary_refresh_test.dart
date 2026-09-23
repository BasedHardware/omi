import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/speaker_summary_action.dart';

ServerConversation conversation(
        {ConversationStatus status = ConversationStatus.completed, String overview = 'Summary'}) =>
    ServerConversation(
        id: 'c',
        createdAt: DateTime(2026),
        structured: Structured('Title', overview),
        status: status,
        transcriptSegments: [
          TranscriptSegment(
              id: 's',
              text: 'Synthetic speech',
              speaker: 'SPEAKER_00',
              isUser: false,
              personId: null,
              translations: [],
              start: 0,
              end: 3)
        ]);

void select(ConversationDetailProvider provider, ServerConversation value) {
  provider.selectedDate = value.createdAt;
  provider.setCachedConversation(value);
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });
  test('transport exception preserves identity and permits an acknowledged retry', () async {
    var fail = true;
    final provider = ConversationDetailProvider(assignSpeaker: (id, ids, {isUser, personId, speakerId}) async {
      if (fail) throw StateError('synthetic transport failure');
      return true;
    });
    select(provider, conversation());
    expect(await provider.assignSpeaker(['s'], 'new'), isFalse);
    expect(provider.conversation.transcriptSegments.single.personId, isNull);
    expect(provider.offerSpeakerSummaryRefresh, isFalse);
    fail = false;
    expect(await provider.assignSpeaker(['s'], 'new'), isTrue);
    expect(provider.conversation.transcriptSegments.single.personId, 'new');
    expect(provider.offerSpeakerSummaryRefresh, isTrue);
    provider.dispose();
  });

  test('only changed acknowledged assignments on summarized completed content offer reprocessing', () async {
    for (final status in [ConversationStatus.completed, ConversationStatus.in_progress]) {
      for (final overview in ['Summary', '']) {
        var saved = false;
        final provider =
            ConversationDetailProvider(assignSpeaker: (id, ids, {isUser, personId, speakerId}) async => saved);
        select(provider, conversation(status: status, overview: overview));
        expect(await provider.assignSpeaker(['s'], 'new'), isFalse);
        expect(provider.conversation.transcriptSegments.single.personId, isNull);
        expect(provider.offerSpeakerSummaryRefresh, isFalse);
        saved = true;
        expect(await provider.assignSpeaker(['s'], 'new'), isTrue);
        expect(provider.offerSpeakerSummaryRefresh, status == ConversationStatus.completed && overview.isNotEmpty);
        provider.dispose();
      }
    }
    final provider = ConversationDetailProvider(assignSpeaker: (id, ids, {isUser, personId, speakerId}) async => true);
    final target = conversation();
    target.transcriptSegments.single.personId = 'same';
    select(provider, target);
    await provider.assignSpeaker(['s'], 'same');
    expect(provider.offerSpeakerSummaryRefresh, isFalse);
    await provider.assignSpeaker(['s'], 'corrected');
    expect(provider.offerSpeakerSummaryRefresh, isTrue);
    provider.dispose();
  });

  testWidgets('explicit action runs once, retains label and retry after failure, replaces detail on success',
      (tester) async {
    final result = Completer<ServerConversation?>();
    int requests = 0;
    bool fail = true;
    final provider = ConversationDetailProvider(
        assignSpeaker: (id, ids, {isUser, personId, speakerId}) async => true,
        reprocess: (id, {appId}) async {
          requests++;
          return fail ? await result.future : conversation(overview: 'Named summary');
        });
    select(provider, conversation());
    await provider.assignSpeaker(['s'], 'new');
    await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: SpeakerSummaryAction(provider: provider))));
    expect(requests, 0);
    await tester.tap(find.byKey(const ValueKey('speaker-summary-refresh')));
    await tester.pump();
    expect(await provider.reprocessConversation(), isFalse);
    expect(await provider.assignSpeaker(['s'], 'racing-edit'), isFalse);
    expect(provider.conversation.transcriptSegments.single.personId, 'new');
    expect(requests, 1);
    result.complete(null);
    await tester.pumpAndSettle();
    expect(provider.offerSpeakerSummaryRefresh, isTrue);
    expect(provider.conversation.transcriptSegments.single.personId, 'new');
    fail = false;
    await tester.tap(find.byKey(const ValueKey('speaker-summary-refresh')));
    await tester.pumpAndSettle();
    expect(requests, 2);
    expect(provider.conversation.structured.overview, 'Named summary');
    expect(provider.offerSpeakerSummaryRefresh, isFalse);
    provider.dispose();
  });

  test('summary reprocessing waits until a pending label save is acknowledged', () async {
    final saved = Completer<bool>();
    int reprocessCalls = 0;
    final provider = ConversationDetailProvider(
        assignSpeaker: (id, ids, {isUser, personId, speakerId}) => saved.future,
        reprocess: (id, {appId}) async {
          reprocessCalls++;
          return null;
        });
    select(provider, conversation());
    final assignment = provider.assignSpeaker(['s'], 'new');
    expect(await provider.reprocessConversation(), isFalse);
    expect(reprocessCalls, 0);
    saved.complete(true);
    expect(await assignment, isTrue);
    expect(provider.offerSpeakerSummaryRefresh, isTrue);
    provider.dispose();
  });
}
