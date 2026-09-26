import 'package:flutter_test/flutter_test.dart';

import 'package:omi/ui/format/omi_plain_text.dart';

void main() {
  test('headings, bullets, quotes and rules drop their markers; lines join into one', () {
    expect(
      OmiPlainText.fromMarkdown('## Summary\n- Pricing leaning annual\n- iOS roadmap set\n> Call Chitapa\n---\n1. Ship'),
      'Summary Pricing leaning annual iOS roadmap set Call Chitapa Ship',
    );
  });

  test('emphasis, code, strike and links keep only their words', () {
    expect(OmiPlainText.fromMarkdown('**Paying users** are _blocked_ by `plan_limit` — see [the doc](https://x.y)'),
        'Paying users are blocked by plan_limit — see the doc');
    expect(OmiPlainText.fromMarkdown('~~old~~ new ![chart](a.png)'), 'old new chart');
  });

  test('plain text and snake_case words are left alone', () {
    expect(OmiPlainText.fromMarkdown('We agreed to ship the revised notes Friday.'),
        'We agreed to ship the revised notes Friday.');
    expect(OmiPlainText.fromMarkdown('rate_limit and user_id stay'), 'rate_limit and user_id stay');
    expect(OmiPlainText.fromMarkdown('2 * 3 = 6'), '2 * 3 = 6');
  });
}
