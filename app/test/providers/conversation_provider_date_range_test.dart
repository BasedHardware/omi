import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/widgets/calendar_date_picker_sheet.dart';

/// Regression tests for the search date-range boundary normalization in
/// ConversationProvider.setSearchDateRange (#4457 / rebase of #7977).
///
/// The date range picker only carries calendar-day granularity, so the end of
/// the selected final day must be included when the range is sent to the API:
/// startDate is floored to 00:00:00.000 and endDate is ceilinged to
/// 23:59:59.999 of the same day. Null on either side means "no limit".
void main() {
  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  ConversationProvider makeProvider({ConversationSearchFetcher? conversationSearchFetcher}) {
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      conversationSearchFetcher: conversationSearchFetcher,
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    return provider;
  }

  group('ConversationProvider.setSearchDateRange day-boundary normalization', () {
    test('endDate is set to the last millisecond of its day', () {
      final provider = makeProvider();
      final midday = DateTime(2026, 6, 15, 13, 30, 45);

      provider.setSearchDateRange(midday, midday);

      expect(provider.searchStartDate, DateTime(2026, 6, 15, 0, 0, 0, 0));
      expect(provider.searchEndDate, DateTime(2026, 6, 15, 23, 59, 59, 999));
    });

    test('a multi-day range includes the full final day', () {
      final provider = makeProvider();
      final start = DateTime(2026, 6, 1, 9, 0);
      final end = DateTime(2026, 6, 30, 17, 0);

      provider.setSearchDateRange(start, end);

      expect(provider.searchStartDate, DateTime(2026, 6, 1));
      expect(provider.searchEndDate, DateTime(2026, 6, 30, 23, 59, 59, 999));
    });

    test('null start leaves the lower bound open', () {
      final provider = makeProvider();
      provider.setSearchDateRange(null, DateTime(2026, 6, 15, 6, 0));

      expect(provider.searchStartDate, isNull);
      expect(provider.searchEndDate, DateTime(2026, 6, 15, 23, 59, 59, 999));
    });

    test('null end leaves the upper bound open', () {
      final provider = makeProvider();
      provider.setSearchDateRange(DateTime(2026, 6, 15, 6, 0), null);

      expect(provider.searchStartDate, DateTime(2026, 6, 15));
      expect(provider.searchEndDate, isNull);
    });

    test('a single selected day falls back to a closed range ending on start', () {
      final start = DateTime(2026, 6, 15, 9);
      expect(closedCalendarRangeEnd(start, null), start);
      expect(closedCalendarRangeEnd(start, DateTime(2026, 6, 20, 17)), DateTime(2026, 6, 20, 17));

      final provider = makeProvider();
      final end = closedCalendarRangeEnd(start, null);
      provider.setSearchDateRange(start, end);

      expect(provider.searchStartDate, DateTime(2026, 6, 15));
      expect(provider.searchEndDate, DateTime(2026, 6, 15, 23, 59, 59, 999));
    });

    test('clearSearchDateRange resets both bounds', () {
      final provider = makeProvider();
      provider.setSearchDateRange(DateTime(2026, 6, 1), DateTime(2026, 6, 30));
      expect(provider.searchStartDate, isNotNull);
      expect(provider.searchEndDate, isNotNull);

      provider.clearSearchDateRange();

      expect(provider.searchStartDate, isNull);
      expect(provider.searchEndDate, isNull);
    });

    test('clearUserData resets search date bounds', () {
      final provider = makeProvider();
      provider.setSearchDateRange(DateTime(2026, 6, 1), DateTime(2026, 6, 30));

      provider.clearUserData();

      expect(provider.searchStartDate, isNull);
      expect(provider.searchEndDate, isNull);
    });
  });

  group('ConversationProvider.searchConversations date range forwarding', () {
    test('searchConversations passes normalized startDate and endDate to the fetcher', () async {
      DateTime? capturedStart;
      DateTime? capturedEnd;
      String? capturedQuery;
      final provider = makeProvider(
        conversationSearchFetcher: (query,
            {page, limit, required includeDiscarded, startDate, endDate, speakerId}) async {
          capturedQuery = query;
          capturedStart = startDate;
          capturedEnd = endDate;
          return (<ServerConversation>[], 1, 1);
        },
      );

      provider.setSearchDateRange(DateTime(2026, 6, 1, 9), DateTime(2026, 6, 30, 17));
      await provider.searchConversations('weekly recap');

      expect(capturedQuery, 'weekly recap');
      expect(capturedStart, DateTime(2026, 6, 1));
      expect(capturedEnd, DateTime(2026, 6, 30, 23, 59, 59, 999));
    });

    test('search date bounds serialize as UTC with an explicit offset', () {
      final localStart = DateTime(2026, 6, 15);
      final localEnd = DateTime(2026, 6, 15, 23, 59, 59, 999);

      final startIso = serializeConversationSearchDateBound(localStart);
      final endIso = serializeConversationSearchDateBound(localEnd);

      expect(localStart.isUtc, isFalse);
      expect(localStart.toIso8601String().contains('Z'), isFalse);
      expect(startIso.endsWith('Z'), isTrue);
      expect(endIso.endsWith('Z'), isTrue);
      expect(DateTime.parse(startIso), localStart.toUtc());
      expect(DateTime.parse(endIso), localEnd.toUtc());
    });

    test('searchMoreConversations keeps the same date bounds', () async {
      DateTime? capturedStart;
      DateTime? capturedEnd;
      final provider = makeProvider(
        conversationSearchFetcher: (query,
            {page, limit, required includeDiscarded, startDate, endDate, speakerId}) async {
          capturedStart = startDate;
          capturedEnd = endDate;
          return (<ServerConversation>[], page ?? 1, 2);
        },
      );

      provider.setSearchDateRange(DateTime(2026, 6, 1), DateTime(2026, 6, 2));
      await provider.searchConversations('hello');
      await provider.searchMoreConversations();

      expect(capturedStart, DateTime(2026, 6, 1));
      expect(capturedEnd, DateTime(2026, 6, 2, 23, 59, 59, 999));
    });
  });
}
