// Whole-row local edits preserve Home presentation without blocking authoritative completion.
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversations/home_rows.dart';
import 'package:omi/pages/activity/past_processing_section.dart';
import 'package:omi/providers/conversation_provider.dart';

ServerConversation row(
        {String? step, ConversationStatus status = ConversationStatus.processing, String title = 'Planning'}) =>
    ServerConversation(
        id: 'c1', createdAt: DateTime(2026, 11, 8), status: status, homeStep: step, structured: Structured(title, ''));

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });
  final replacements = <String, void Function(ConversationProvider, ServerConversation)>{
    'update by id': (p, c) => p.updateConversation(c),
    'update by index': (p, c) => p.updateConversation(c, index: 0),
    'insertion': (p, c) {
      p.conversations.clear();
      p.addConversation(c);
    },
    'upsert': (p, c) => p.upsertConversation(c),
    'sorted/grouped replacement': (p, c) => p.updateConversationInSortedList(c),
    'grouped insertion': (p, c) {
      p.conversations.clear();
      p.addConversationWithDateGrouped(c);
    },
    'bridge survivor': (p, c) => p.replaceBridgedConversation('donor', c),
  };
  for (final step in <String?>['failed', 'transcribing', 'writing_notes', 'ready', null]) {
    for (final replacement in replacements.entries) {
      test('${replacement.key} retains home_step=$step when omitted', () {
        // Bridge replacement accepts completed survivors. Same-status local edits must
        // preserve the projection even without a remembered processing id.
        final status = replacement.key == 'bridge survivor' || step == 'ready'
            ? ConversationStatus.completed
            : ConversationStatus.processing;
        final original = row(step: step, status: status);
        final provider = ConversationProvider(isSignedIn: () => false)
          ..conversations = [original]
          ..searchedConversations = [original];
        addTearDown(provider.dispose);
        provider.groupConversationsByDate();
        final incoming = row(status: status, title: 'Edited planning');
        replacement.value(provider, incoming);
        expect(provider.conversations.last.homeStep, step);
        expect(provider.conversations.last.structured.title, 'Edited planning');
        if (step == null) expect(provider.conversations.last, same(incoming));
      });
    }
  }
  for (final step in <String?>['failed', null]) {
    test('search replacement and pagination retain home_step=$step', () async {
      final provider = ConversationProvider(
        isSignedIn: () => true,
        conversationSearchResultFetcher: (query,
                {page, limit, required includeDiscarded, startDate, endDate, speakerId}) async =>
            ConversationSearchResult(
                items: [row()],
                currentPage: page ?? 1,
                totalPages: 2,
                outcome: ConversationSearchResultOutcome.success),
      )..conversations = [row(step: step)];
      addTearDown(provider.dispose);
      await provider.searchConversations('planning');
      expect(provider.searchedConversations.single.homeStep, step);
      await provider.searchMoreConversations();
      expect(provider.searchedConversations, hasLength(2));
      expect(provider.searchedConversations.map((c) => c.homeStep), everyElement(step));
    });
  }
  test('known failure survives replacement after the original row leaves the list', () {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    provider.addProcessingConversation(row(step: 'failed'));
    provider.conversations.clear();
    provider.addConversationWithDateGrouped(row());
    expect(provider.conversations.single.homeStep, 'failed');
    expect(provider.processingConversations, isEmpty);
  });
  test('an active replacement retains a failed current row even when stored status differs', () {
    final provider = ConversationProvider(isSignedIn: () => false)
      ..conversations = [row(step: 'failed', status: ConversationStatus.completed)];
    addTearDown(provider.dispose);
    provider.updateConversation(row());
    expect(provider.conversations.single.homeStep, 'failed');
  });
  for (final status in [ConversationStatus.in_progress, ConversationStatus.processing, ConversationStatus.merging]) {
    test('retry to $status without home_step immediately clears the failure', () {
      final failed = row(step: 'failed');
      final provider = ConversationProvider(isSignedIn: () => false)
        ..conversations = [failed]
        ..searchedConversations = [failed];
      addTearDown(provider.dispose);
      // Also exercise the remembered failure id, beyond the row's wire field.
      provider.addProcessingConversation(failed);
      provider.applyConversationReprocessResult(row(status: status));
      if (status != ConversationStatus.in_progress) {
        expect(provider.conversations, isEmpty);
        expect(provider.searchedConversations, isEmpty);
        expect(provider.processingConversations, hasLength(1));
      }
      final updated = [...provider.processingConversations, ...provider.conversations].single;
      expect(updated.homeStep, isNull);
      expect(updated.status, status);
      expect(isFailedHomeConversation(updated), isFalse);
      expect(
          failedActivityConversations(pending: [], conversations: [
            ...provider.searchedConversations,
            ...provider.processingConversations,
            ...provider.conversations
          ]),
          isEmpty);
    });
  }
  test('off-page search retry updates shared processing state without a loaded row', () {
    final provider = ConversationProvider(isSignedIn: () => false)..searchedConversations = [row(step: 'failed')];
    addTearDown(provider.dispose);
    // Search has moved to a different page by the time retry returns.
    provider.searchedConversations.clear();
    provider.applyConversationReprocessResult(row(status: ConversationStatus.processing));
    expect(provider.processingConversations.single.homeStep, isNull);
    expect(
        failedActivityConversations(
          pending: [],
          conversations: [
            ...provider.searchedConversations,
            ...provider.processingConversations,
            ...provider.conversations
          ],
        ),
        isEmpty);
  });
  test('fresh completed reprocess clears a failed projection on an already completed row', () {
    final provider = ConversationProvider(isSignedIn: () => false)
      ..conversations = [row(step: 'failed', status: ConversationStatus.completed)];
    addTearDown(provider.dispose);
    provider.applyConversationReprocessResult(row(status: ConversationStatus.completed));
    expect(provider.conversations.single.homeStep, isNull);
  });
  test('authoritative reprocess also clears a search-only failed projection', () {
    final provider = ConversationProvider(isSignedIn: () => false)
      ..searchedConversations = [row(step: 'failed', status: ConversationStatus.completed)];
    addTearDown(provider.dispose);
    provider.applyConversationReprocessResult(row(status: ConversationStatus.completed));
    expect(provider.conversations.single.homeStep, isNull);
  });
  for (final step in <String?>['failed', null]) {
    test('calendar copies retain home_step=$step without a list provider masking the copy', () async {
      final event = CalendarEventLink(
          eventId: 'event', title: 'Planning', startTime: DateTime(2026, 11, 8), endTime: DateTime(2026, 11, 8, 1));
      final original = row(step: step);
      final detail = ConversationDetailProvider(
        linkCalendar: (id, eventId) async {
          expect(id, 'c1');
          expect(eventId, event.eventId);
          return event;
        },
        unlinkCalendar: (_) async => true,
        autoLinkCalendar: (_) async => event,
      )
        ..selectedDate = conversationLocalDayKey(original.createdAt)
        ..setCachedConversation(original);
      addTearDown(detail.dispose);
      expect(await detail.linkCalendarEvent('event'), same(event));
      expect(detail.conversation.calendarEvent, same(event));
      expect(detail.conversation.homeStep, step);
      expect(await detail.unlinkCalendarEvent(), isTrue);
      expect(detail.conversation.calendarEvent, isNull);
      expect(detail.conversation.homeStep, step);
      expect(await detail.autoLinkCalendarEvent(), same(event));
      expect(detail.conversation.homeStep, step);
    });
  }
}
