import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/conversation_provider.dart';

/// Regression tests for the search date-range boundary normalization in
/// ConversationProvider.setSearchDateRange.
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

  group('ConversationProvider.setSearchDateRange day-boundary normalization', () {
    test('endDate is set to the last millisecond of its day', () {
      final provider = ConversationProvider();
      final midday = DateTime(2026, 6, 15, 13, 30, 45);

      provider.setSearchDateRange(midday, midday);

      expect(provider.searchStartDate, DateTime(2026, 6, 15, 0, 0, 0, 0));
      // End of the selected final calendar day must be included.
      expect(provider.searchEndDate, DateTime(2026, 6, 15, 23, 59, 59, 999));
    });

    test('a multi-day range includes the full final day', () {
      final provider = ConversationProvider();
      final start = DateTime(2026, 6, 1, 9, 0);
      final end = DateTime(2026, 6, 30, 17, 0);

      provider.setSearchDateRange(start, end);

      expect(provider.searchStartDate, DateTime(2026, 6, 1));
      expect(provider.searchEndDate, DateTime(2026, 6, 30, 23, 59, 59, 999));
    });

    test('null start leaves the lower bound open', () {
      final provider = ConversationProvider();
      provider.setSearchDateRange(null, DateTime(2026, 6, 15, 6, 0));

      expect(provider.searchStartDate, isNull);
      expect(provider.searchEndDate, DateTime(2026, 6, 15, 23, 59, 59, 999));
    });

    test('null end leaves the upper bound open', () {
      final provider = ConversationProvider();
      provider.setSearchDateRange(DateTime(2026, 6, 15, 6, 0), null);

      expect(provider.searchStartDate, DateTime(2026, 6, 15));
      expect(provider.searchEndDate, isNull);
    });

    test('clearSearchDateRange resets both bounds', () {
      final provider = ConversationProvider();
      provider.setSearchDateRange(DateTime(2026, 6, 1), DateTime(2026, 6, 30));
      expect(provider.searchStartDate, isNotNull);
      expect(provider.searchEndDate, isNotNull);

      provider.clearSearchDateRange();

      expect(provider.searchStartDate, isNull);
      expect(provider.searchEndDate, isNull);
    });
  });
}
