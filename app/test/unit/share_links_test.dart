import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/share_links.dart';

void main() {
  group('shareBaseUrl', () {
    test('defaults to production h.omi.me', () {
      expect(shareBaseUrl(''), defaultShareBaseUrl);
      expect(shareBaseUrl(null), defaultShareBaseUrl);
    });

    test('honors overrides and strips trailing slash', () {
      expect(shareBaseUrl('https://share.example.com/'), 'https://share.example.com');
      expect(shareBaseUrl('share.example.com'), 'https://share.example.com');
    });

    test('falls back for malformed overrides', () {
      expect(shareBaseUrl('ftp://share.example.com'), defaultShareBaseUrl);
      expect(shareBaseUrl('not a url'), defaultShareBaseUrl);
    });
  });

  group('typed share URLs', () {
    test('conversation / app / recap paths', () {
      expect(
        conversationShareUrl('c1', raw: 'https://share.example.com'),
        'https://share.example.com/conversations/c1',
      );
      expect(appShareUrl('a1', raw: 'https://share.example.com'), 'https://share.example.com/apps/a1');
      expect(recapShareUrl('r1', raw: 'https://share.example.com'), 'https://share.example.com/recaps/r1');
    });
  });
}
