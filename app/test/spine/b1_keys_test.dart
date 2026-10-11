import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/dev_controls/addressability.dart';

import '../support/spine/contract.dart';

void main() {
  contractTest('B1 stable row identities survive ordering and do not expose record IDs', () {
    pendingContract('B1');
    final first = AddressKey.row('conversations', 'record-a');
    final second = AddressKey.row('conversations', 'record-b');
    expect(first, matches(RegExp(r'^omi\.conversations\.row\.r[0-9a-f]{64}$')));
    expect(first, 'omi.conversations.row.re12c02249bf145590a804eb574fe92f28cf5bbb95ab536c1fbcfb79d342fa640');
    expect(first, isNot(second));
    expect(AddressKey.row('chat', 'record-a'), isNot(first));
    expect(['record-b', 'record-a'].map((id) => AddressKey.row('conversations', id)), [second, first]);
    expect(AddressKey.valid(first), isTrue);
    expect(first.contains('record-a'), isFalse);
    expect(() => AddressKey.row('conversations', ''), throwsArgumentError);
    expect(() => AddressKey.row('conversations', 'a' * 257), throwsArgumentError);
    expect(() => AddressKey.row('unknown', 'record-a'), throwsArgumentError);
  });
  contractTest('B1 key grammar is exact, including optional qualifier', () {
    pendingContract('B1');
    for (final key in ['omi.chat.input', 'omi.conversations.row.rabc0123', 'omi.tasks.toggle.done_today']) {
      expect(AddressKey.valid(key), isTrue, reason: key);
    }
    for (final key in [
      'chat.send',
      'omi.Chat.send',
      'omi.chat',
      'omi.chat.send.',
      'omi.chat.send.a.b',
      ' omi.chat.send',
      'omi.chat.send\n',
      'omi.chat.send.email@local.test'
    ]) {
      expect(AddressKey.valid(key), isFalse, reason: key);
    }
  });
}
