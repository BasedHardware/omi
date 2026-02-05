import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shimmer/shimmer.dart';

import 'package:omi/widgets/shimmer_with_timeout.dart';

void main() {
  testWidgets('shows shimmer before timeout and hides after', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: ShimmerWithTimeout(
          timeoutSeconds: 1,
          child: SizedBox(width: 10, height: 10),
        ),
      ),
    );

    expect(find.byType(Shimmer), findsOneWidget);

    await tester.pump(const Duration(seconds: 1));
    await tester.pump();

    expect(find.byType(Shimmer), findsNothing);
  });

  testWidgets('does not throw when disposed before timeout', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: ShimmerWithTimeout(
          timeoutSeconds: 2,
          child: SizedBox(width: 10, height: 10),
        ),
      ),
    );

    await tester.pumpWidget(const MaterialApp(home: SizedBox.shrink()));
    await tester.pump(const Duration(seconds: 3));

    expect(tester.takeException(), isNull);
  });
}
