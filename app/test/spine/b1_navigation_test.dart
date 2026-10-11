import 'package:flutter_test/flutter_test.dart';
import 'package:omi/flavors.dart';
import 'package:omi/services/dev_controls/addressability.dart';

import '../support/spine/contract.dart';

void main() {
  contractTest('B1 navigator rejects absent opt-in or absent mounted owner without changing routes', () async {
    pendingContract('B1');
    F.env = Environment.dev;
    final api = AppAddressability.instance;
    expect(api.rootMounted, isFalse);
    expect(api.visibleRoute, isNull);
    const expected = String.fromEnvironment('OMI_DEV_CONTROLS') == '1' ? 'unmounted' : 'ineligible';
    await expectLater(
        api.navigate('chat'), throwsA(isA<AddressabilityRefused>().having((e) => e.code, 'code', expected)));
    expect(api.visibleRoute, isNull);
    expect(api.pendingTransitions, 0);
  });
  contractTest('B1 navigator refuses production-family profile before touching navigation', () async {
    pendingContract('B1');
    final previous = F.env;
    try {
      F.env = Environment.prod;
      await expectLater(AppAddressability.instance.navigate('chat'),
          throwsA(isA<AddressabilityRefused>().having((e) => e.code, 'code', 'ineligible')));
    } finally {
      F.env = previous;
    }
  });
}
