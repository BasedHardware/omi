/// The share sheet must always get a non-empty anchor rect.
///
/// iPad and macOS present it as a popover and `share_plus` throws a
/// PlatformException when the origin is missing or zero-sized. Share calls are
/// typically the last await in a button handler, so that exception goes
/// unhandled and the button silently does nothing — which is how the device
/// diagnostics export appeared broken.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/share_sheet.dart';

void main() {
  group('shareSheetOrigin', () {
    test('falls back to a non-empty rect when there is no anchor key', () {
      final rect = shareSheetOrigin();

      expect(rect.isEmpty, isFalse);
      expect(rect, equals(kFallbackShareOrigin));
    });

    test('falls back when the key was never attached to a widget', () {
      final rect = shareSheetOrigin(GlobalKey());

      expect(rect.isEmpty, isFalse);
    });

    testWidgets('returns the anchor widget rect once laid out', (tester) async {
      final key = GlobalKey();
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Center(child: SizedBox(key: key, width: 48, height: 24)),
          ),
        ),
      );

      final rect = shareSheetOrigin(key);

      expect(rect.width, 48);
      expect(rect.height, 24);
      expect(rect.isEmpty, isFalse);
      // Anchored to the real widget, not the corner fallback.
      expect(rect, isNot(equals(kFallbackShareOrigin)));
    });

    testWidgets('falls back rather than returning an empty rect for a zero-sized anchor', (tester) async {
      final key = GlobalKey();
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Center(child: SizedBox(key: key, width: 0, height: 0)),
          ),
        ),
      );

      final rect = shareSheetOrigin(key);

      expect(rect.isEmpty, isFalse, reason: 'an empty rect is exactly what makes share_plus throw');
      expect(rect, equals(kFallbackShareOrigin));
    });
  });
}
