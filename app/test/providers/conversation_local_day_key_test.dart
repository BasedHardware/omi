import 'package:flutter_test/flutter_test.dart';

import 'package:omi/providers/conversation_provider.dart';

/// Regression coverage for #10198: conversations were bucketed into day-groups by
/// their raw UTC calendar day, while the date filter used the local `selectedDate`,
/// so an early-morning-local conversation vanished from "Today" for UTC+ viewers.
///
/// Note on limits: `DateTime.toLocal()` uses the ambient timezone, which is UTC on
/// CI, so this cannot reproduce the UTC-vs-local divergence there — it locks the
/// helper's contract (local-day truncation) and catches a revert to raw-UTC on any
/// non-UTC host. On-device confirmation in a UTC+ timezone is the end-to-end proof.
void main() {
  group('conversationLocalDayKey', () {
    test('truncates a timestamp to its local calendar day (time-of-day stripped)', () {
      final ts = DateTime.utc(2026, 7, 20, 20, 48); // 20:48 UTC
      final key = conversationLocalDayKey(ts);
      final local = ts.toLocal();

      expect(key, DateTime(local.year, local.month, local.day));
      expect(key.hour, 0);
      expect(key.minute, 0);
      expect(key.second, 0);
      expect(key.isUtc, isFalse);
    });

    test('two moments in the same local day share a bucket; the next local day differs', () {
      final anchor = DateTime.utc(2026, 7, 20, 2, 0).toLocal();
      final sameDayLater = DateTime(anchor.year, anchor.month, anchor.day, 23, 30);
      final nextDay = DateTime(anchor.year, anchor.month, anchor.day).add(const Duration(days: 1));

      expect(conversationLocalDayKey(sameDayLater), conversationLocalDayKey(anchor));
      expect(conversationLocalDayKey(nextDay), isNot(conversationLocalDayKey(anchor)));
    });
  });
}
