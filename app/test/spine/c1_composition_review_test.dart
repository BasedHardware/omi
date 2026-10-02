import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/capture/capture_composition.dart';
import '../support/spine/contract.dart';
import 'c1_composition_test.dart' show dependencies, MemoryPrefs;

class BatchPrefs extends MemoryPrefs {
  bool muted = true;
  @override
  bool get batchMuted => muted;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  contractTest('C1 injected preferences remain authoritative after construction', () {
    final prefs = BatchPrefs();
    final p = composeCaptureProvider(dependencies(preferences: prefs));
    try {
      // No singleton initialization. Catching a global read is an assertion failure.
      expect(() => p.offlineMuted, returnsNormally);
      expect(p.offlineMuted, isTrue);
      prefs.muted = false;
      expect(p.offlineMuted, isFalse);
    } finally {
      p.dispose();
    }
  });
}
