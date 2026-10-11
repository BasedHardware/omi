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

ServerConversation conversation({
  String id = 'c',
  ConversationStatus status = ConversationStatus.completed,
  String overview = 'Summary',
}) =>
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
          end: 3,
        ),
      ],
    );

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

  testWidgets('explicit action runs once, retains label and retry after failure, replaces detail on success', (
    tester,
  ) async {
    final result = Completer<ServerConversation?>();
    int requests = 0;
    bool fail = true;
    final provider = ConversationDetailProvider(
      assignSpeaker: (id, ids, {isUser, personId, speakerId}) async => true,
      reprocess: (id, {appId, requireSpeakerReceipt = false}) async {
        requests++;
        return fail ? await result.future : conversation(overview: 'Named summary');
      },
    );
    select(provider, conversation());
    expect(await provider.assignSpeaker(['s'], 'new'), isTrue);
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: SpeakerSummaryAction(provider: provider)),
      ),
    );
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
      },
    );
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
    target.transcriptSegments.add(
      TranscriptSegment(
        id: 's2',
        text: 'Second synthetic voice',
        speaker: 'SPEAKER_01',
        isUser: false,
        personId: null,
        translations: [],
        start: 4,
        end: 7,
      ),
    );
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
    expect(provider.trackedSpeakerConversationIds, isEmpty);
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
      fetchConversation: (id) async => conversation(id: id),
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
    expect(provider.trackedSpeakerConversationIds, isEmpty);
    await tester.pump(const Duration(seconds: 4));
    expect(reprocessCalls, 1);
  });

  testWidgets('leaving while a save is in flight regenerates once after acknowledgement', (tester) async {
    final save = Completer<bool>();
    final refreshedIds = <String>[];
    final provider = ConversationDetailProvider(
      assignSpeaker: (id, ids, {isUser, personId, speakerId}) => save.future,
      fetchConversation: (id) async => conversation(id: id),
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
      fetchConversation: (id) async => conversation(id: id),
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
    expect(provider.trackedSpeakerConversationIds, isEmpty);
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
    expect(provider.trackedSpeakerConversationIds, isEmpty);
  });

  testWidgets('deleting during an in-flight label save drops its refresh', (tester) async {
    final save = Completer<bool>();
    final list = ConversationProvider();
    final target = conversation();
    var fetches = 0;
    var regenerations = 0;
    final provider = ConversationDetailProvider(
      assignSpeaker: (id, ids, {isUser, personId, speakerId}) => save.future,
      fetchConversation: (id) async {
        fetches++;
        return target;
      },
      reprocess: (id, {appId, requireSpeakerReceipt = false}) async {
        regenerations++;
        return null;
      },
    );
    provider.conversationProvider = list;
    select(provider, target);
    final assignment = provider.assignSpeaker(['s'], 'named-person');
    list.memoriesToDelete[target.id] = target; // The delete-with-Undo tombstone.
    provider.dispose();
    save.complete(true);

    expect(await assignment, isTrue);
    await tester.pump(const Duration(seconds: 4));
    expect(fetches, 0);
    expect(regenerations, 0);
    expect(provider.trackedSpeakerConversationIds, isEmpty);
    list.dispose();
  });

  testWidgets('missing detail after exit cannot trigger regeneration', (tester) async {
    var regenerations = 0;
    final provider = ConversationDetailProvider(
      assignSpeaker: (id, ids, {isUser, personId, speakerId}) async => true,
      fetchConversation: (id) async => null,
      reprocess: (id, {appId, requireSpeakerReceipt = false}) async {
        regenerations++;
        return null;
      },
    );
    select(provider, conversation());
    expect(await provider.assignSpeaker(['s'], 'named-person'), isTrue);
    provider.dispose();
    await tester.pump();
    expect(regenerations, 0);
    expect(provider.trackedSpeakerConversationIds, isEmpty);
  });

  testWidgets('completed and failed labeling sessions release tracking', (tester) async {
    final provider = ConversationDetailProvider(
      assignSpeaker: (id, ids, {isUser, personId, speakerId}) async => id == 'saved',
      reprocess: (id, {appId, requireSpeakerReceipt = false}) async => conversation(id: id),
    );
    select(provider, conversation(id: 'saved'));
    expect(await provider.assignSpeaker(['s'], 'named-person'), isTrue);
    await tester.pump(const Duration(seconds: 4));
    expect(provider.trackedSpeakerConversationIds, isEmpty);

    select(provider, conversation(id: 'failed'));
    expect(await provider.assignSpeaker(['s'], 'named-person'), isFalse);
    expect(provider.trackedSpeakerConversationIds, isEmpty);
    provider.dispose();
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
    expect(list.groupedConversations.values.expand((group) => group).map((conversation) => conversation.id), [
      survivorId,
    ]);
    expect(await provider.assignSpeaker(['s'], 'other-person'), isTrue);
    expect(assignedIds, [donorId, survivorId]);
    await tester.pump(const Duration(seconds: 4));
    provider.dispose();
    list.dispose();
  });

  group('labeling pass', () {
    ServerConversation twoVoices({String id = 'c'}) {
      final value = conversation(id: id);
      value.transcriptSegments.add(
        TranscriptSegment(
          id: 's2',
          text: 'Second synthetic voice',
          speaker: 'SPEAKER_01',
          isUser: false,
          personId: null,
          translations: [],
          start: 4,
          end: 7,
        ),
      );
      return value;
    }

    ({ConversationDetailProvider provider, List<String> reprocessed, List<(String, bool?, String?)> saves}) harness({
      Future<bool> Function()? save,
    }) {
      final reprocessed = <String>[];
      final saves = <(String, bool?, String?)>[];
      final provider = ConversationDetailProvider(
        assignSpeaker: (id, ids, {isUser, personId, speakerId}) {
          saves.add((ids.join(','), isUser, personId));
          return save?.call() ?? Future.value(true);
        },
        fetchConversation: (id) async => twoVoices(id: id),
        reprocess: (id, {appId, requireSpeakerReceipt = false}) async {
          expectSync(requireSpeakerReceipt, isTrue);
          reprocessed.add(id);
          return twoVoices(id: id);
        },
      );
      select(provider, twoVoices());
      return (provider: provider, reprocessed: reprocessed, saves: saves);
    }

    testWidgets('pauses between labels never regenerate; Done regenerates once', (tester) async {
      final h = harness();
      h.provider.beginSpeakerLabelingSession();
      expect(h.provider.speakerLabelingSessionActive, isTrue);
      expect(await h.provider.assignSpeaker(['s'], 'maya'), isTrue);
      await tester.pump(const Duration(seconds: 10));
      expect(await h.provider.assignSpeaker(['s2'], 'jordan'), isTrue);
      await tester.pump(const Duration(seconds: 10));
      expect(h.reprocessed, isEmpty);
      expect(h.provider.speakerLabelingSessionLineCount, 2);

      h.provider.confirmSpeakerLabelingSession();
      expect(h.provider.speakerLabelingSessionActive, isFalse);
      expect(h.reprocessed, ['c']);
      await tester.pump();
      h.provider.confirmSpeakerLabelingSession();
      h.provider.leaveSpeakerLabelingSession('c');
      await tester.pump(const Duration(seconds: 10));
      expect(h.reprocessed, ['c']);
      h.provider.dispose();
      await tester.pump();
      expect(h.reprocessed, ['c']);
    });

    testWidgets('a pass that changed nothing regenerates nothing', (tester) async {
      final h = harness();
      h.provider.beginSpeakerLabelingSession();
      h.provider.confirmSpeakerLabelingSession();
      await tester.pump(const Duration(seconds: 10));
      expect(h.reprocessed, isEmpty);
      expect(h.provider.trackedSpeakerConversationIds, isEmpty);
      h.provider.dispose();
    });

    testWidgets('Done while a save is in flight regenerates once, after it lands', (tester) async {
      final save = Completer<bool>();
      final h = harness(save: () => save.future);
      h.provider.beginSpeakerLabelingSession();
      final assignment = h.provider.assignSpeaker(['s'], 'maya');
      h.provider.confirmSpeakerLabelingSession();
      expect(h.reprocessed, isEmpty);
      save.complete(true);
      expect(await assignment, isTrue);
      await tester.pump();
      expect(h.reprocessed, ['c']);
      await tester.pump(const Duration(seconds: 10));
      expect(h.reprocessed, ['c']);
      expect(h.provider.trackedSpeakerConversationIds, isEmpty);
      h.provider.dispose();
    });

    testWidgets('leaving the page mid-pass auto-confirms once; Done afterwards is a no-op', (tester) async {
      final h = harness();
      h.provider.beginSpeakerLabelingSession();
      expect(await h.provider.assignSpeaker(['s'], 'maya'), isTrue);
      h.provider.leaveSpeakerLabelingSession('another-conversation');
      expect(h.provider.speakerLabelingSessionActive, isTrue);
      h.provider.leaveSpeakerLabelingSession('c');
      expect(h.provider.speakerLabelingSessionActive, isFalse);
      await tester.pump();
      expect(h.reprocessed, ['c']);
      h.provider.confirmSpeakerLabelingSession();
      h.provider.dispose();
      await tester.pump(const Duration(seconds: 10));
      expect(h.reprocessed, ['c']);
      expect(h.provider.trackedSpeakerConversationIds, isEmpty);
    });

    testWidgets('a page under another detail page cannot end the top one\'s pass', (tester) async {
      final h = harness();
      h.provider.beginSpeakerLabelingSession();
      expect(await h.provider.assignSpeaker(['s'], 'maya'), isTrue);
      h.provider.confirmSpeakerLabelingSession(conversationId: 'page-underneath');
      expect(h.provider.speakerLabelingSessionActive, isTrue);
      expect(h.reprocessed, isEmpty);
      h.provider.confirmSpeakerLabelingSession(conversationId: 'c');
      expect(h.reprocessed, ['c']);
      await tester.pump();
      h.provider.dispose();
    });

    testWidgets('labeling again after Done starts a new pass with its own single regeneration', (tester) async {
      final h = harness();
      h.provider.beginSpeakerLabelingSession();
      expect(await h.provider.assignSpeaker(['s'], 'maya'), isTrue);
      h.provider.confirmSpeakerLabelingSession();
      await tester.pump();
      expect(h.reprocessed, ['c']);

      h.provider.beginSpeakerLabelingSession();
      expect(h.provider.speakerLabelingSessionLineCount, 0);
      expect(await h.provider.assignSpeaker(['s2'], 'jordan'), isTrue);
      await tester.pump(const Duration(seconds: 10));
      expect(h.reprocessed, ['c']);
      h.provider.confirmSpeakerLabelingSession();
      await tester.pump();
      expect(h.reprocessed, ['c', 'c']);
      h.provider.dispose();
    });

    testWidgets('switching conversations mid-pass flushes the old pass through the exit path', (tester) async {
      final h = harness();
      h.provider.beginSpeakerLabelingSession();
      expect(await h.provider.assignSpeaker(['s'], 'maya'), isTrue);
      select(h.provider, twoVoices(id: 'next'));
      expect(h.provider.speakerLabelingSessionActive, isFalse);
      await tester.pump();
      expect(h.reprocessed, ['c']);
      await tester.pump(const Duration(seconds: 10));
      expect(h.reprocessed, ['c']);
      h.provider.dispose();
    });

    testWidgets('Undo puts back and re-saves each line\'s previous label', (tester) async {
      final h = harness();
      final segments = h.provider.conversation.transcriptSegments;
      segments.first.personId = 'alex';
      segments.last.isUser = true;
      h.provider.beginSpeakerLabelingSession();
      expect(h.provider.canUndoSpeakerLabel, isFalse);
      expect(await h.provider.assignSpeaker(['s', 's2'], 'maya'), isTrue);
      expect(segments.map((s) => (s.isUser, s.personId)), [(false, 'maya'), (false, 'maya')]);
      expect(h.provider.speakerLabelingSessionLineCount, 2);
      expect(h.provider.canUndoSpeakerLabel, isTrue);

      expect(await h.provider.undoLastSpeakerLabel(), isTrue);
      expect(segments.map((s) => (s.isUser, s.personId)), [(false, 'alex'), (true, null)]);
      expect(h.saves, [
        ('s,s2', false, 'maya'),
        ('s', false, 'alex'),
        ('s2', true, null),
      ]);
      expect(h.provider.speakerLabelingSessionLineCount, 0);
      expect(h.provider.canUndoSpeakerLabel, isFalse);
      expect(h.provider.speakerLabelingSessionActive, isTrue);
      await tester.pump(const Duration(seconds: 10));
      expect(h.reprocessed, isEmpty);
      h.provider.dispose();
    });

    testWidgets('a failed Undo leaves the lines as the server still has them', (tester) async {
      var accept = true;
      final h = harness(save: () async => accept);
      final segment = h.provider.conversation.transcriptSegments.first;
      h.provider.beginSpeakerLabelingSession();
      expect(await h.provider.assignSpeaker(['s'], 'maya'), isTrue);
      accept = false;
      expect(await h.provider.undoLastSpeakerLabel(), isFalse);
      expect(segment.personId, 'maya');
      expect(h.provider.canUndoSpeakerLabel, isFalse);
      h.provider.dispose();
    });

    testWidgets('an Undo that saves only some of its labels leaves every line as the server has it', (tester) async {
      final server = <String, (bool, String?)>{'s': (false, 'alex'), 's2': (true, null)};
      var undoSaves = 0;
      var undoing = false;
      final provider = ConversationDetailProvider(
        assignSpeaker: (id, ids, {isUser, personId, speakerId}) async {
          // The second grouped restore fails after the first one landed.
          if (undoing && ++undoSaves == 2) return false;
          for (final segmentId in ids) {
            server[segmentId] = (isUser ?? false, personId);
          }
          return true;
        },
        fetchConversation: (id) async => twoVoices(id: id),
        reprocess: (id, {appId, requireSpeakerReceipt = false}) async => twoVoices(id: id),
      );
      select(provider, twoVoices());
      final segments = provider.conversation.transcriptSegments;
      segments.first.personId = 'alex';
      segments.last.isUser = true;
      provider.beginSpeakerLabelingSession();
      expect(await provider.assignSpeaker(['s', 's2'], 'maya'), isTrue);

      undoing = true;
      expect(await provider.undoLastSpeakerLabel(), isFalse);
      expect(undoSaves, 2);
      expect(server, {'s': (false, 'alex'), 's2': (false, 'maya')});
      expect({for (final s in segments) s.id: (s.isUser, s.personId)}, server);
      provider.dispose();
    });

    testWidgets('a sync bridge mid-pass keeps the pass open; Done regenerates the survivor once', (tester) async {
      const donorId = '00000000-0000-5000-8000-000000000001';
      const survivorId = '3883d17e-0000-4000-8000-000000000000';
      final fetched = <String>[];
      final reprocessed = <String>[];
      final provider = ConversationDetailProvider(
        assignSpeaker: (id, ids, {isUser, personId, speakerId}) async => true,
        fetchConversation: (id) async {
          fetched.add(id);
          return twoVoices(id: survivorId);
        },
        reprocess: (id, {appId, requireSpeakerReceipt = false}) async {
          expectSync(requireSpeakerReceipt, isTrue);
          reprocessed.add(id);
          return twoVoices(id: id);
        },
      );
      select(provider, twoVoices(id: donorId));
      provider.beginSpeakerLabelingSession();
      expect(await provider.assignSpeaker(['s'], 'maya'), isTrue);
      expect(fetched, [donorId]);
      expect(provider.conversation.id, survivorId);
      expect(provider.speakerLabelingSessionActive, isTrue);
      expect(provider.speakerLabelingSessionLineCount, 1);
      expect(provider.canUndoSpeakerLabel, isTrue);
      await tester.pump(const Duration(seconds: 10));
      expect(reprocessed, isEmpty);

      // The page still holds the donor ID: it ends its own pass, a page underneath still cannot.
      provider.confirmSpeakerLabelingSession(conversationId: 'page-underneath');
      expect(provider.speakerLabelingSessionActive, isTrue);
      provider.confirmSpeakerLabelingSession(conversationId: donorId);
      expect(provider.speakerLabelingSessionActive, isFalse);
      expect(reprocessed, [survivorId]);
      await tester.pump();
      provider.leaveSpeakerLabelingSession(donorId);
      await tester.pump(const Duration(seconds: 10));
      expect(reprocessed, [survivorId]);
      provider.dispose();
    });

    testWidgets('Done or leaving with the bridging save in flight regenerates the survivor once', (tester) async {
      const donorId = '00000000-0000-5000-8000-000000000001';
      const survivorId = '3883d17e-0000-4000-8000-000000000000';
      for (final leave in [false, true]) {
        final save = Completer<bool>();
        final reprocessed = <String>[];
        final provider = ConversationDetailProvider(
          assignSpeaker: (id, ids, {isUser, personId, speakerId}) => save.future,
          fetchConversation: (id) async => twoVoices(id: survivorId),
          reprocess: (id, {appId, requireSpeakerReceipt = false}) async {
            reprocessed.add(id);
            return twoVoices(id: id);
          },
        );
        select(provider, twoVoices(id: donorId));
        provider.beginSpeakerLabelingSession();
        final assignment = provider.assignSpeaker(['s'], 'maya');
        if (leave) {
          provider.leaveSpeakerLabelingSession(donorId);
        } else {
          provider.confirmSpeakerLabelingSession(conversationId: donorId);
        }
        expect(provider.speakerLabelingSessionActive, isFalse);
        save.complete(true);
        expect(await assignment, isTrue);
        await tester.pump();
        expect(reprocessed, [survivorId], reason: leave ? 'leave' : 'Done');
        await tester.pump(const Duration(seconds: 10));
        expect(reprocessed, [survivorId], reason: leave ? 'leave' : 'Done');
        provider.dispose();
      }
    });

    testWidgets('a label that failed to save is not counted and has nothing to undo', (tester) async {
      final h = harness(save: () async => false);
      h.provider.beginSpeakerLabelingSession();
      expect(await h.provider.assignSpeaker(['s'], 'maya'), isFalse);
      expect(h.provider.speakerLabelingSessionLineCount, 0);
      expect(h.provider.canUndoSpeakerLabel, isFalse);
      h.provider.dispose();
    });
  });
}
