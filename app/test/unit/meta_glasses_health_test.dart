import 'package:flutter_test/flutter_test.dart';
import 'package:meta_wearables_dat_flutter/meta_wearables_dat_flutter.dart';
import 'package:omi/providers/meta_wearables_provider.dart';

void main() {
  group('Meta glasses health mapping', () {
    test('maps DAT thermal and hinge session errors to user-facing health states', () {
      expect(
        MetaGlassesHealth.fromSessionError(
          const SessionError(code: DatErrorCodes.thermalCritical, message: 'hot'),
        ),
        MetaGlassesHealth.overheating,
      );
      expect(
        MetaGlassesHealth.fromSessionError(
          const SessionError(code: DatErrorCodes.hingesClosed, message: 'folded'),
        ),
        MetaGlassesHealth.foldedClosed,
      );
      expect(
        MetaGlassesHealth.fromSessionError(
          const SessionError(code: DatErrorCodes.timeout, message: 'timeout'),
        ),
        isNull,
      );
    });
  });
}
