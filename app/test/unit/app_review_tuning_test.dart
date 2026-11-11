import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/app_review_tuning.dart';

void main() {
  test('accepts bounded integer flag payloads and defaults on invalid values', () {
    expect(AppReviewTuning.parseInt({'reading_seconds': 8}, 'reading_seconds', 5, 30), 8);
    expect(AppReviewTuning.parseInt({'reading_seconds': 0}, 'reading_seconds', 5, 30), 5);
    expect(AppReviewTuning.parseInt({'reading_seconds': 31}, 'reading_seconds', 5, 30), 5);
    expect(AppReviewTuning.parseInt({'reading_seconds': '8'}, 'reading_seconds', 5, 30), 5);
    expect(AppReviewTuning.parseInt('{"reading_seconds":8}', 'reading_seconds', 5, 30), 8);
    expect(AppReviewTuning.parseInt(null, 'reading_seconds', 5, 30), 5);
    expect(AppReviewTuning.parseInt({'cooldown_days': 60}, 'cooldown_days', 30, 365), 60);
  });
}
