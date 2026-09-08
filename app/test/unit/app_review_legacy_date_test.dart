import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/app.dart';

/// Regression tests for the cached apps-list crash:
///
/// FlutterError — FormatException: Invalid field: responded_at
/// at _readFieldValue → GeneratedAppReview.fromJson → App.fromJson
/// → SharedPreferencesUtil.appsList (startup, AnalyticsManager.identify).
///
/// AppReview.toJson used to serialize null updatedAt/respondedAt as '',
/// which the strict generated wire parser rejects when the cached apps
/// list is read back on the next launch.
void main() {
  Map<String, dynamic> minimalAppJson({List<Map<String, dynamic>>? reviews, Map<String, dynamic>? userReview}) {
    return {
      'id': 'app-1',
      'name': 'Test App',
      'author': 'Tester',
      'category': 'productivity',
      'description': 'desc',
      'image': 'img.png',
      'capabilities': <String>[],
      if (reviews != null) 'reviews': reviews,
      if (userReview != null) 'user_review': userReview,
    };
  }

  Map<String, dynamic> reviewJson({dynamic respondedAt, dynamic updatedAt}) {
    return {
      'uid': 'user-1',
      'rated_at': '2026-07-01T10:00:00.000Z',
      'score': 4.0,
      'review': 'nice app',
      'responded_at': respondedAt,
      'updated_at': updatedAt,
    };
  }

  group('legacy cached apps list with empty-string review dates', () {
    test('App.fromJson parses a review with responded_at == "" (crash case)', () {
      final app = App.fromJson(
        minimalAppJson(
          reviews: [reviewJson(respondedAt: '', updatedAt: '')],
        ),
      );
      expect(app.reviews, hasLength(1));
      expect(app.reviews.first.respondedAt, isNull);
    });

    test('App.fromJson parses a user_review with responded_at == ""', () {
      final app = App.fromJson(
        minimalAppJson(
          userReview: reviewJson(respondedAt: '', updatedAt: ''),
        ),
      );
      expect(app.userReview, isNotNull);
      expect(app.userReview!.respondedAt, isNull);
    });

    test('App.fromJson still parses valid responded_at values', () {
      final app = App.fromJson(minimalAppJson(reviews: [reviewJson(respondedAt: '2026-07-02T09:00:00.000Z')]));
      expect(app.reviews.first.respondedAt, isNotNull);
    });

    test('AppReview.fromJson parses responded_at == ""', () {
      final review = AppReview.fromJson(reviewJson(respondedAt: '', updatedAt: ''));
      expect(review.respondedAt, isNull);
      expect(review.updatedAt, isNull);
    });
  });

  group('AppReview.toJson no longer writes empty-string dates', () {
    test('null dates serialize as null and survive a cache round-trip', () {
      final review = AppReview(uid: 'user-1', ratedAt: DateTime.utc(2026, 7, 1, 10), score: 4.0, review: 'nice app');
      final json = review.toJson();
      expect(json['responded_at'], isNull);
      expect(json['updated_at'], isNull);

      final roundTripped = App.fromJson(minimalAppJson(reviews: [json]));
      expect(roundTripped.reviews.first.respondedAt, isNull);
    });
  });
}
