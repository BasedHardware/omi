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
      expect(shareBaseUrl('https://share.example.com?x=1'), defaultShareBaseUrl);
      expect(shareBaseUrl('https://share.example.com#frag'), defaultShareBaseUrl);
      expect(shareBaseUrl('https://user:pass@share.example.com'), defaultShareBaseUrl);
    });

    test('preserves path prefix without query or fragment', () {
      expect(shareBaseUrl('https://share.example.com/omi/'), 'https://share.example.com/omi');
      expect(
        conversationShareUrl('c1', raw: 'https://share.example.com/omi/', source: 'ios', sid: 'sid12345'),
        'https://share.example.com/omi/conversations/c1?s=ios&sid=sid12345',
      );
    });
  });

  group('typed share URLs', () {
    test('conversation / app / recap paths', () {
      expect(
        conversationShareUrl('c1', raw: 'https://share.example.com', source: 'android', sid: 'sid12345'),
        'https://share.example.com/conversations/c1?s=android&sid=sid12345',
      );
      expect(
        appShareUrl('a1', raw: 'https://share.example.com', source: 'ios', sid: 'sid12345'),
        'https://share.example.com/apps/a1?s=ios&sid=sid12345',
      );
      expect(
        recapShareUrl('r1', raw: 'https://share.example.com', source: 'android', sid: 'sid12345'),
        'https://share.example.com/recaps/r1?s=android&sid=sid12345',
      );
    });

    test('new share ID is random and non-identifying', () {
      final first = newShareId();
      final second = newShareId();
      expect(first, matches(RegExp(r'^[0-9a-f]{32}$')));
      expect(first, isNot(second));
    });

    test('tags backend-issued task URL while preserving its query', () {
      expect(
        tagShareUrl('https://h.omi.me/tasks/token?existing=1', source: 'ios', sid: 'sid12345'),
        'https://h.omi.me/tasks/token?existing=1&s=ios&sid=sid12345',
      );
    });

    test('reported share-sheet target is a bounded app category', () {
      expect(shareTargetApp('com.whatsapp.WhatsApp.ShareExtension'), 'whatsapp');
      expect(shareTargetApp('com.apple.UIKit.activity.CopyToPasteboard'), 'copy');
      expect(shareTargetApp('dev.fluttercommunity.plus/share/unavailable'), null);
      expect(shareTargetApp('arbitrary.package.with.user.details'), 'other');
    });
  });
}
