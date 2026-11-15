import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import '../../integration_test/perf/heavy_storage_budget.dart';

void main() {
  late Directory temporary;
  late Directory root;
  setUp(() async {
    temporary = await Directory.systemTemp.createTemp('heavy-budget-test-');
    root = Directory('${temporary.path}/owned-fixture-namespace');
  });
  tearDown(() async {
    // Tests create only empty directories and synthetic JSON, never WAL/audio.
    await temporary.delete(recursive: true);
  });

  test('allocation cap survives fresh budget instances without deleting earlier fixtures', () async {
    final first = await HeavyStorageBudget(root, limit: 2).reserve();
    final second = await HeavyStorageBudget(root, limit: 2).reserve();
    expect(second.path, isNot(first.path));
    await expectLater(HeavyStorageBudget(root, limit: 2).reserve(), throwsStateError);
    expect(await first.exists(), isTrue);
    expect(await second.exists(), isTrue);
    final ledger = jsonDecode(await File('${root.path}/allocations.json').readAsString());
    expect(ledger['allocated'], 2);
  });

  test('unowned or corrupt namespace fails closed without modifying contents', () async {
    await root.create();
    await expectLater(HeavyStorageBudget(root).reserve(), throwsStateError);
    final ledger = File('${root.path}/allocations.json');
    await ledger.writeAsString('{"schema":"unknown","allocated":0}');
    await expectLater(HeavyStorageBudget(root).reserve(), throwsStateError);
    expect(await ledger.readAsString(), '{"schema":"unknown","allocated":0}');
  });

  test('a consumed reservation cannot be reclaimed by deleting an empty run directory', () async {
    final first = await HeavyStorageBudget(root, limit: 1).reserve();
    await first.delete(); // Empty synthetic test directory, no audio.
    await expectLater(HeavyStorageBudget(root, limit: 1).reserve(), throwsStateError);
  });
}
