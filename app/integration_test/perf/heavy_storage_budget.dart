import 'dart:convert';
import 'dart:io';

/// Append-only reservations bound fixture accumulation without deleting audio.
/// A crash after reservation consumes a slot; it cannot silently reclaim data.
class HeavyStorageBudget {
  HeavyStorageBudget(this.root, {this.limit = 24});
  final Directory root;
  final int limit;

  Future<Directory> reserve() async {
    final ledger = File('${root.path}/allocations.json');
    var allocated = 0;
    if (await root.exists()) {
      if (!await ledger.exists()) throw StateError('Synthetic fixture namespace has no ownership ledger; stop.');
      final raw = jsonDecode(await ledger.readAsString());
      if (raw is! Map || raw['schema'] != 'omi-heavy-fixture-budget/v1' || raw['allocated'] is! int) {
        throw StateError('Unreadable synthetic fixture allocation ledger; stop.');
      }
      allocated = raw['allocated'] as int;
    } else {
      await root.create();
    }
    if (allocated < 0 || allocated >= limit) {
      throw StateError('Synthetic fixture allocation cap reached; ask owner. No WAL/audio is removed.');
    }
    final pending = File('${ledger.path}.pending');
    await pending.writeAsString(jsonEncode({'schema': 'omi-heavy-fixture-budget/v1', 'allocated': allocated + 1}),
        flush: true);
    await pending.rename(ledger.path);
    return root.createTemp('run-');
  }
}
