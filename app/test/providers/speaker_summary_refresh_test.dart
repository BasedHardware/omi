import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api/conversations.dart' show hasSpeakerReceiptSummaryCapability;
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/speaker_summary_action.dart';
import 'package:omi/providers/conversation_provider.dart';

ServerConversation conversation(
        {String id = 'c', ConversationStatus status = ConversationStatus.completed, String overview = 'Summary'}) =>
    ServerConversation(
        id: id,
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
  test('older backend responses cannot acknowledge receipt-aware summaries', () {
    expect(hasSpeakerReceiptSummaryCapability({}), isFalse);
    expect(hasSpeakerReceiptSummaryCapability({'x-omi-speaker-receipt-summary': '0'}), isFalse);
    expect(hasSpeakerReceiptSummaryCapability({'x-omi-speaker-receipt-summary': '1'}), isTrue);
  });

  testWidgets('transport exception preserves identity and permits an acknowledged retry', (tester) async {
    var fail = true;
    var reprocessCalls = 0;
    final provider = ConversationDetailProvider(
      assignSpeaker: (id, ids, {isUser, personId, speakerId}) async {
        if (fail) throw StateError('synthetic transport failure');
        return true;
      },
      reprocess: (id, {appId, requireSpeakerReceipt = false}) async {
        reprocessCalls++;
        expectSync(requireSpeakerReceipt, isTrue);
        final refreshed = conversation(overview: 'Named summary');
        refreshed.transcriptSegments.single.personId = 'new';
        return refreshed;
      },
    );
    select(provider, conversation());
    expect(await provider.assignSpeaker(['s'], 'new'), isFalse);
    expect(provider.conversation.transcriptSegments.single.personId, isNull);
    expect(provider.offerSpeakerSummaryRefresh, isFalse);
    fail = false;
    expect(await provider.assignSpeaker(['s'], 'new'), isTrue);
    expect(provider.conversation.transcriptSegments.single.personId, 'new');
    expect(reprocessCalls, 0);
    await tester.pump(const Duration(seconds: 4));
    expect(provider.offerSpeakerSummaryRefresh, isFalse);
    expect(reprocessCalls, 1);
    provider.dispose();
  });

  testWidgets('only changed acknowledged assignments on summarized completed content regenerate once', (tester) async {
    for (final status in [ConversationStatus.completed, ConversationStatus.in_progress]) {
      for (final overview in ['Summary', '']) {
        var saved = false;
        var reprocessCalls = 0;
        final provider = ConversationDetailProvider(
          assignSpeaker: (id, ids, {isUser, personId, speakerId}) async => saved,
          reprocess: (id, {appId, requireSpeakerReceipt = false}) async {
            reprocessCalls++;
            return conversation(overview: 'Named summary');
          },
        );
        select(provider, conversation(status: status, overview: overview));
        expect(await provider.assignSpeaker(['s'], 'new'), isFalse);
        expect(provider.conversation.transcriptSegments.single.personId, isNull);
        expect(provider.offerSpeakerSummaryRefresh, isFalse);
        saved = true;
        expect(await provider.assignSpeaker(['s'], 'new'), isTrue);
        expect(reprocessCalls, 0);
        await tester.pump(const Duration(seconds: 4));
        expect(reprocessCalls, status == ConversationStatus.completed && overview.isNotEmpty ? 1 : 0);
        expect(provider.offerSpeakerSummaryRefresh, isFalse);
        provider.dispose();
      }
    }
    var reprocessCalls = 0;
    final provider = ConversationDetailProvider(
      assignSpeaker: (id, ids, {isUser, personId, speakerId}) async => true,
      reprocess: (id, {appId, requireSpeakerReceipt = false}) async {
        reprocessCalls++;
        return conversation(overview: 'Named summary');
      },
    );
    final target = conversation();
    target.transcriptSegments.single.personId = 'same';
    select(provider, target);
    await provider.assignSpeaker(['s'], 'same');
    expect(provider.offerSpeakerSummaryRefresh, isFalse);
    expect(reprocessCalls, 0);
    await provider.assignSpeaker(['s'], 'corrected');
    await tester.pump(const Duration(seconds: 4));
    expect(reprocessCalls, 1);
    expect(provider.offerSpeakerSummaryRefresh, isFalse);
    provider.dispose();
  });

  testWidgets('explicit action runs once, retains label and retry after failure, replaces detail on success',
      (tester) async {
    final result = Completer<ServerConversation?>();
    int requests = 0;
    bool fail = true;
    final provider = ConversationDetailProvider(
        assignSpeaker: (id, ids, {isUser, personId, speakerId}) async => true,
        reprocess: (id, {appId, requireSpeakerReceipt = false}) async {
          requests++;
          return fail ? await result.future : conversation(overview: 'Named summary');
        });
    select(provider, conversation());
    expect(await provider.assignSpeaker(['s'], 'new'), isTrue);
    await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: SpeakerSummaryAction(provider: provider))));
    expect(requests, 0);
    await tester.pump(const Duration(seconds: 4));
    expect(requests, 1);
    expect(await provider.reprocessConversation(), isFalse);
    expect(await provider.assignSpeaker(['s'], 'racing-edit'), isFalse);
    expect(provider.conversation.transcriptSegments.single.personId, 'new');
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

  testWidgets('summary reprocessing waits until a pending label save is acknowledged', (tester) async {
    final saved = Completer<bool>();
    int reprocessCalls = 0;
    final provider = ConversationDetailProvider(
        assignSpeaker: (id, ids, {isUser, personId, speakerId}) => saved.future,
        reprocess: (id, {appId, requireSpeakerReceipt = false}) async {
          reprocessCalls++;
          return null;
        });
    select(provider, conversation());
    final assignment = provider.assignSpeaker(['s'], 'new');
    expect(await provider.reprocessConversation(), isFalse);
    expect(reprocessCalls, 0);
    saved.complete(true);
    expect(await assignment, isTrue);
    expect(reprocessCalls, 0);
    await tester.pump(const Duration(seconds: 4));
    expect(reprocessCalls, 1);
    expect(provider.offerSpeakerSummaryRefresh, isTrue);
    provider.dispose();
  });

  testWidgets('queued corrections regenerate only after the final saved label', (tester) async {
    final firstSave = Completer<bool>();
    final assigned = <String>[];
    var reprocessCalls = 0;
    final provider = ConversationDetailProvider(
      assignSpeaker: (id, ids, {isUser, personId, speakerId}) {
        assigned.add(personId!);
        return firstSave.future;
      },
      reprocess: (id, {appId, requireSpeakerReceipt = false}) async {
        reprocessCalls++;
        return null;
      },
    );
    select(provider, conversation());
    final first = provider.assignSpeaker(['s'], 'first');
    final second = provider.assignSpeaker(['s'], 'second');
    expect(reprocessCalls, 0);
    firstSave.complete(true);
    expect(await first, isFalse);
    expect(await second, isTrue);
    expect(assigned, ['second']);
    expect(reprocessCalls, 0);
    await tester.pump(const Duration(seconds: 4));
    expect(reprocessCalls, 1);
    expect(provider.conversation.transcriptSegments.single.personId, 'second');
    provider.dispose();
  });

  testWidgets('separately completed speaker labels share one quiet-period regeneration', (tester) async {
    var reprocessCalls = 0;
    final provider = ConversationDetailProvider(
      assignSpeaker: (id, ids, {isUser, personId, speakerId}) async => true,
      reprocess: (id, {appId, requireSpeakerReceipt = false}) async {
        expectSync(requireSpeakerReceipt, isTrue);
        reprocessCalls++;
        return null;
      },
    );
    final target = conversation();
    target.transcriptSegments.add(TranscriptSegment(
        id: 's2',
        text: 'Second synthetic voice',
        speaker: 'SPEAKER_01',
        isUser: false,
        personId: null,
        translations: [],
        start: 4,
        end: 7));
    select(provider, target);

    expect(await provider.assignSpeaker(['s'], 'first-person'), isTrue);
    await tester.pump(const Duration(seconds: 2));
    expect(reprocessCalls, 0);
    expect(await provider.assignSpeaker(['s2'], 'second-person'), isTrue);
    await tester.pump(const Duration(seconds: 3));
    expect(reprocessCalls, 0);
    await tester.pump(const Duration(seconds: 1));
    expect(reprocessCalls, 1);
    provider.dispose();
  });

  testWidgets('failed regeneration is not retried by a no-op save', (tester) async {
    var reprocessCalls = 0;
    final provider = ConversationDetailProvider(
      assignSpeaker: (id, ids, {isUser, personId, speakerId}) async => true,
      reprocess: (id, {appId, requireSpeakerReceipt = false}) async {
        expectSync(requireSpeakerReceipt, isTrue);
        reprocessCalls++;
        if (reprocessCalls == 1) return null; // Older backend lacked the capability header.
        final refreshed = conversation(overview: 'Named summary');
        refreshed.transcriptSegments.single.personId = 'named-person';
        return refreshed;
      },
    );
    select(provider, conversation());

    expect(await provider.assignSpeaker(['s'], 'named-person'), isTrue);
    await tester.pump(const Duration(seconds: 4));
    expect(reprocessCalls, 1);
    expect(provider.offerSpeakerSummaryRefresh, isTrue);
    expect(await provider.assignSpeaker(['s'], 'named-person'), isTrue);
    await tester.pump(const Duration(seconds: 4));
    expect(reprocessCalls, 1);
    expect(provider.offerSpeakerSummaryRefresh, isTrue);
    expect(await provider.reprocessConversation(), isTrue);
    expect(reprocessCalls, 2);
    expect(provider.offerSpeakerSummaryRefresh, isFalse);
    provider.dispose();
  });

  testWidgets('leaving detail flushes one pending regeneration', (tester) async {
    var reprocessCalls = 0;
    final provider = ConversationDetailProvider(
      assignSpeaker: (id, ids, {isUser, personId, speakerId}) async => true,
      reprocess: (id, {appId, requireSpeakerReceipt = false}) async {
        expectSync(requireSpeakerReceipt, isTrue);
        reprocessCalls++;
        return null;
      },
    );
    select(provider, conversation());

    expect(await provider.assignSpeaker(['s'], 'named-person'), isTrue);
    provider.dispose();
    await tester.pump();
    expect(reprocessCalls, 1);
    await tester.pump(const Duration(seconds: 4));
    expect(reprocessCalls, 1);
  });

  testWidgets('leaving while a save is in flight regenerates once after acknowledgement', (tester) async {
    final save = Completer<bool>();
    final refreshedIds = <String>[];
    final provider = ConversationDetailProvider(
      assignSpeaker: (id, ids, {isUser, personId, speakerId}) => save.future,
      reprocess: (id, {appId, requireSpeakerReceipt = false}) async {
        expectSync(requireSpeakerReceipt, isTrue);
        refreshedIds.add(id);
        return null;
      },
    );
    select(provider, conversation(id: 'first'));
    final assignment = provider.assignSpeaker(['s'], 'named-person');
    provider.dispose();
    expect(refreshedIds, isEmpty);

    save.complete(true);
    expect(await assignment, isTrue);
    await tester.pump();
    expect(refreshedIds, ['first']);
    await tester.pump(const Duration(seconds: 4));
    expect(refreshedIds, ['first']);
  });

  testWidgets('switching conversations mid-save refreshes the saved conversation', (tester) async {
    final save = Completer<bool>();
    final refreshedIds = <String>[];
    final provider = ConversationDetailProvider(
      assignSpeaker: (id, ids, {isUser, personId, speakerId}) => id == 'first' ? save.future : Future.value(true),
      reprocess: (id, {appId, requireSpeakerReceipt = false}) async {
        refreshedIds.add(id);
        return null;
      },
    );
    select(provider, conversation(id: 'first'));
    final firstAssignment = provider.assignSpeaker(['s'], 'named-person');
    select(provider, conversation(id: 'second'));
    final secondAssignment = provider.assignSpeaker(['s'], 'second-person');
    save.complete(true);

    expect(await firstAssignment, isTrue);
    expect(await secondAssignment, isTrue);
    await tester.pump();
    expect(refreshedIds, ['first']);
    expect(provider.conversation.id, 'second');
    expect(provider.offerSpeakerSummaryRefresh, isTrue);
    await tester.pump(const Duration(seconds: 4));
    expect(refreshedIds, ['first', 'second']);
    provider.dispose();
    await tester.pump(const Duration(seconds: 4));
    expect(refreshedIds, ['first', 'second']);
  });

  testWidgets('leaving during a failed save never regenerates', (tester) async {
    final save = Completer<bool>();
    var regenerations = 0;
    final provider = ConversationDetailProvider(
      assignSpeaker: (id, ids, {isUser, personId, speakerId}) => save.future,
      reprocess: (id, {appId, requireSpeakerReceipt = false}) async {
        regenerations++;
        return null;
      },
    );
    select(provider, conversation());
    final assignment = provider.assignSpeaker(['s'], 'named-person');
    provider.dispose();
    save.complete(false);

    expect(await assignment, isFalse);
    await tester.pump(const Duration(seconds: 4));
    expect(regenerations, 0);
  });

  testWidgets('ended sync donor refresh follows the bridged conversation', (tester) async {
    const donorId = '00000000-0000-5000-8000-000000000001';
    const survivorId = '3883d17e-0000-4000-8000-000000000000';
    final save = Completer<bool>();
    final refreshedIds = <String>[];
    final provider = ConversationDetailProvider(
      assignSpeaker: (id, ids, {isUser, personId, speakerId}) => save.future,
      fetchConversation: (id) async {
        expectSync(id, donorId);
        return conversation(id: survivorId);
      },
      reprocess: (id, {appId, requireSpeakerReceipt = false}) async {
        refreshedIds.add(id);
        return null;
      },
    );
    select(provider, conversation(id: donorId));
    final assignment = provider.assignSpeaker(['s'], 'named-person');
    provider.dispose();
    save.complete(true);

    expect(await assignment, isTrue);
    await tester.pump();
    expect(refreshedIds, [survivorId]);
  });

  testWidgets('a speaker save adopts the bridged survivor and removes the retired list row', (tester) async {
    const donorId = '00000000-0000-5000-8000-000000000001';
    const survivorId = '3883d17e-0000-4000-8000-000000000000';
    final donor = conversation(id: donorId);
    final survivor = conversation(id: survivorId);
    final list = ConversationProvider();
    list.conversations.add(donor);
    list.groupedConversations[conversationLocalDayKey(donor.createdAt)] = [donor];
    final fetchedIds = <String>[];
    final assignedIds = <String>[];
    final provider = ConversationDetailProvider(
      assignSpeaker: (id, ids, {isUser, personId, speakerId}) async {
        assignedIds.add(id);
        return true;
      },
      fetchConversation: (id) async {
        fetchedIds.add(id);
        return survivor;
      },
      reprocess: (id, {appId, requireSpeakerReceipt = false}) async => null,
    );
    provider.conversationProvider = list;
    select(provider, donor);

    expect(await provider.assignSpeaker(['s'], 'person'), isTrue);
    expect(fetchedIds, [donorId]);
    expect(provider.conversation.id, survivorId);
    expect(list.conversations.map((conversation) => conversation.id), [survivorId]);
    expect(
        list.groupedConversations.values.expand((group) => group).map((conversation) => conversation.id), [survivorId]);
    expect(await provider.assignSpeaker(['s'], 'other-person'), isTrue);
    expect(assignedIds, [donorId, survivorId]);
    await tester.pump(const Duration(seconds: 4));
    provider.dispose();
    list.dispose();
  });
}
