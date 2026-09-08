import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/pages/apps/app_detail/reviews_section.dart';

void main() {
  testWidgets('rating distribution renders its score, count, and five-star scale', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: RatingDistributionWidget(
            ratingAvg: 4.2,
            ratingCount: 7,
            reviews: [],
          ),
        ),
      ),
    );

    expect(find.text('4.2'), findsOneWidget);
    expect(find.text('7 ratings'), findsOneWidget);
    expect(find.byType(FaIcon), findsNWidgets(5));
  });
}
