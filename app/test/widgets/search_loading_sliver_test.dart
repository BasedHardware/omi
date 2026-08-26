import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/apps/widgets/search_loading_sliver.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

/// The shimmer placeholders stop animating after [ShimmerWithTimeout]'s timeout
/// and fall back to static blocks. A search that takes longer than that is then
/// indistinguishable from a frozen screen, which is the bug these tests pin.
Future<void> _pumpLoadingState(WidgetTester tester) async {
  await tester.pumpWidget(
    const MaterialApp(
      home: Scaffold(body: CustomScrollView(slivers: [SearchLoadingSliver()])),
    ),
  );
}

void main() {
  group('search loading state', () {
    testWidgets('shows placeholder rows while the search runs', (tester) async {
      await _pumpLoadingState(tester);

      expect(find.byType(ShimmerWithTimeout), findsNWidgets(5));
    });

    testWidgets('still shows a running progress indicator after the shimmer has timed out', (tester) async {
      await _pumpLoadingState(tester);

      // Past ShimmerWithTimeout's 5s fallback, where the placeholders go static.
      await tester.pump(const Duration(seconds: 10));

      // The user must still be able to tell the search is running rather than wedged.
      expect(find.byType(LinearProgressIndicator), findsOneWidget);
    });

    testWidgets('the progress indicator is indeterminate, because search has no known duration', (tester) async {
      await _pumpLoadingState(tester);
      await tester.pump(const Duration(seconds: 10));

      final indicator = tester.widget<LinearProgressIndicator>(find.byType(LinearProgressIndicator));

      // A determinate bar would have to invent a percentage; a stuck one at a fixed
      // value is exactly the "is it working?" doubt this is meant to remove.
      expect(indicator.value, isNull);
    });
  });
}
