import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/conversations/v3_live_row_visibility.dart';

void main() {
  for (final serverUsable in [false, true]) {
    final serverOrNone = serverUsable ? V3HomeLiveRow.server : V3HomeLiveRow.none;
    for (final streaming in [false, true]) {
      for (final (v3Home, removed, call, suppressed, reason, expected) in [
        (
          true,
          false,
          false,
          false,
          'default Home',
          streaming && !serverUsable ? V3HomeLiveRow.placeholder : serverOrNone
        ),
        (false, false, false, false, 'outside v3 Home', V3HomeLiveRow.none),
        (true, true, false, false, 'removed', V3HomeLiveRow.none),
        (true, false, true, false, 'call active', serverOrNone),
        (true, false, false, true, 'after Finish', serverOrNone),
      ]) {
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
