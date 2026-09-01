import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/home/home_content.dart';

void main() {
  group('day timeline short-conversation collapsing', () {
    test('collapses sub-two-minute captures by default', () {
      expect(homeShortConversationThreshold(showShortConversations: false, userThreshold: 0), 120);
    });

    test('keeps a stricter threshold the user set themselves', () {
      expect(homeShortConversationThreshold(showShortConversations: false, userThreshold: 300), 300);
    });

    test('collapses nothing once the user asks to see short conversations', () {
      expect(homeShortConversationThreshold(showShortConversations: true, userThreshold: 300), 0);
    });
  });
}
