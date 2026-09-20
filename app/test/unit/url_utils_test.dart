import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/url_utils.dart';

void main() {
  test('adds uid to a URL without a query', () {
    expect(withUidQueryParameter('https://example.com/connect', 'user-1'), 'https://example.com/connect?uid=user-1');
  });

  test('preserves existing query parameters and fragment', () {
    expect(
      withUidQueryParameter('https://example.com/connect?source=omi#finish', 'user-1'),
      'https://example.com/connect?source=omi&uid=user-1#finish',
    );
  });

  test('replaces a stale uid instead of duplicating it', () {
    expect(
      withUidQueryParameter('https://example.com/connect?uid=old&source=omi', 'user-1'),
      'https://example.com/connect?uid=user-1&source=omi',
    );
  });
}
