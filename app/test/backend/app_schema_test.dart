import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/app.dart';

Map<String, dynamic> _appJson({Object? reviews = _missingReviews}) {
  final json = <String, dynamic>{
    'id': 'app-1',
    'name': 'Review parser',
    'author': 'Omi',
    'description': 'Parses reviews',
    'image': 'https://example.com/icon.png',
    'category': 'productivity',
    'capabilities': ['chat'],
    'rating_count': 0,
    'enabled': true,
    'approved': true,
    'private': false,
  };

  if (!identical(reviews, _missingReviews)) {
    json['reviews'] = reviews;
  }

  return json;
}

const _missingReviews = Object();

void main() {
  group('App review parsing', () {
    test('defaults missing reviews to an empty list', () {
      final app = App.fromJson(_appJson());

      expect(app.reviews, isEmpty);
    });

    test('defaults null reviews to an empty list', () {
      final app = App.fromJson(_appJson(reviews: null));

      expect(app.reviews, isEmpty);
    });

    test('keeps empty reviews as an empty list', () {
      final app = App.fromJson(_appJson(reviews: []));

      expect(app.reviews, isEmpty);
    });

    test('parses present reviews', () {
      final app = App.fromJson(
        _appJson(
          reviews: [
            {
              'uid': 'review-1',
              'rated_at': '2026-07-01T12:00:00.000Z',
              'score': 5.0,
              'review': 'Helpful',
              'username': 'Reviewer',
              'response': 'Thanks',
              'responded_at': '2026-07-02T12:00:00.000Z',
            },
          ],
        ),
      );

      expect(app.reviews, hasLength(1));
      expect(app.reviews.single.uid, 'review-1');
      expect(app.reviews.single.score, 5.0);
      expect(app.reviews.single.review, 'Helpful');
      expect(app.reviews.single.username, 'Reviewer');
      expect(app.reviews.single.response, 'Thanks');
      expect(app.reviews.single.respondedAt, isNotNull);
    });
  });
}
