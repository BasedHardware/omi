import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/experiments/plan_storefront_gate.dart';

void main() {
  test('contextual flags start in parallel and require both opt-ins', () async {
    final pending = <String, Completer<bool>>{};
    final result = PlanStorefrontGate.contextualEnabled(readFlag: (key) {
      final flag = Completer<bool>();
      pending[key] = flag;
      return flag.future;
    });
    expect(pending.keys, containsAll([PlanStorefrontGate.sheetFlag, PlanStorefrontGate.upsellFlag]));
    for (final flag in pending.values) {
      flag.complete(false);
    }
    expect(await result, isFalse);
  });
  test('both surface flags default off and errors fail closed', () async {
    expect(await PlanStorefrontGate.sheetEnabled(readFlag: (_) async => false), isFalse);
    expect(await PlanStorefrontGate.upsellsEnabled(readFlag: (_) async => throw StateError('offline')), isFalse);
  });
  test('sheet and contextual moments are separate opt-ins', () async {
    final keys = <String>[];
    Future<bool> read(String key) async {
      keys.add(key);
      return key == PlanStorefrontGate.sheetFlag;
    }

    expect(await PlanStorefrontGate.sheetEnabled(readFlag: read), isTrue);
    expect(await PlanStorefrontGate.upsellsEnabled(readFlag: read), isFalse);
    expect(keys, ['mobile-plan-storefront', 'mobile-contextual-upsells']);
  });
}
