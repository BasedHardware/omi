import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/experiments/plan_storefront_gate.dart';

void main() {
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
