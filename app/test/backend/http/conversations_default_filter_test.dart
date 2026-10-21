import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/conversations.dart';

void main() {
  test('conversation collection hides discarded rows by default', () {
    final defaultUrl = Uri.parse(conversationCollectionUrl('https://example.test'));
    final explicitUrl = Uri.parse(conversationCollectionUrl('https://example.test', includeDiscarded: true));

    expect(defaultUrl.queryParameters['include_discarded'], 'false');
    expect(explicitUrl.queryParameters['include_discarded'], 'true');
  });
}
