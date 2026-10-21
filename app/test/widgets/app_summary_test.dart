import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/pages/apps/app_detail/app_summary.dart';

void main() {
  testWidgets('app summary expands for a long title instead of overflowing', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 220,
            child: AppDetailSummary(
              name: 'RPG Translator: Speak Gamer, Think Human',
              author: 'Omi',
              official: false,
              ratingCount: 0,
              rating: '0.0',
              installs: 0,
              action: SizedBox(width: 75, height: 32),
            ),
          ),
        ),
      ),
    );

    expect(tester.takeException(), isNull);
    expect(tester.getSize(find.byType(AppDetailSummary)).height, greaterThan(108));
  });
}
