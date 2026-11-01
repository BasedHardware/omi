import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/experiments/summary_generation_gate.dart';

void main() {
  tearDown(() {
    SummaryGenerationV2Gate.debugOverride = null;
  });

  group('SummaryGenerationV2Gate.refresh fencing', () {
    test('clears the cached value while a read is pending (fail-closed)', () async {
      SummaryGenerationV2Gate.debugOverride = null;
      var completeRead = Completer<bool>();
      final published = <bool>[];

      final refresh = SummaryGenerationV2Gate.refresh(
        readFlag: (_) => completeRead.future,
      );
      // While the read is pending the gate must read off, not keep a stale true.
      expect(SummaryGenerationV2Gate.isEnabled, isFalse);

      completeRead.complete(true);
      published.add(await refresh);
      expect(published, [true]);
      expect(SummaryGenerationV2Gate.isEnabled, isTrue);
    });

    test('an older overlapping read cannot overwrite a newer decision', () async {
      SummaryGenerationV2Gate.debugOverride = null;
      final olderRead = Completer<bool>();
      final newerRead = Completer<bool>();

      final older = SummaryGenerationV2Gate.refresh(readFlag: (_) => olderRead.future);
      final newer = SummaryGenerationV2Gate.refresh(readFlag: (_) => newerRead.future);

      newerRead.complete(true);
      expect(await newer, isTrue);
      // The older read finishing late must not flip the gate back off.
      olderRead.complete(false);
      await older;
      expect(SummaryGenerationV2Gate.isEnabled, isTrue);
    });

    test('a failed read leaves the redesign off', () async {
      SummaryGenerationV2Gate.debugOverride = null;
      final result = await SummaryGenerationV2Gate.refresh(
        readFlag: (_) => Future.error(StateError('no analytics identity')),
      );
      expect(result, isFalse);
      expect(SummaryGenerationV2Gate.isEnabled, isFalse);
    });
  });
}
