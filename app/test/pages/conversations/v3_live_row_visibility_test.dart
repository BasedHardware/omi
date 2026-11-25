import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/conversations/v3_live_row_visibility.dart';

void main() {
  for (final serverUsable in [false, true]) {
    for (final streaming in [false, true]) {
      for (final (v3Home, removed, call, suppressed, reason) in [
        (true, false, false, false, 'default Home'),
        (false, false, false, false, 'outside v3 Home'),
        (true, true, false, false, 'removed'),
        (true, false, true, false, 'call active'),
        (true, false, false, true, 'after Finish'),
      ]) {
        final expected = !v3Home || removed || (streaming && (call || suppressed))
            ? V3HomeLiveRow.none
            : serverUsable
                ? V3HomeLiveRow.server
                : streaming
                    ? V3HomeLiveRow.placeholder
                    : V3HomeLiveRow.none;
        test('$reason, streaming=$streaming, usable server=$serverUsable shows ${expected.name}', () {
          expect(
            v3HomeLiveRow(
              v3Home: v3Home,
              streaming: streaming,
              serverUsable: serverUsable,
              liveRemoved: removed,
              callActive: call,
              listeningSuppressed: suppressed,
            ),
            expected,
          );
        });
      }
    }
  }
}
