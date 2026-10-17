import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/mobile/native_ui/native_button_projection.dart';
import 'package:omi/ui/components/omi_button.dart';

void main() {
  test('original actions run only after selection; disabled and unknown controls are retained', () async {
    var calls = 0;
    final rows = nativeButtonRows([
      OmiButton(key: const Key('save'), label: 'Save', onPressed: () async => calls++),
      const SizedBox(height: 8),
      Wrap(children: [
        TextButton(key: const Key('skip'), onPressed: () => calls += 10, child: const Text('Skip')),
        const OmiButton(label: 'Wait', onPressed: null),
      ]),
    ], prefix: 'voice')!;
    expect(calls, 0);
    expect(rows.last.projection['enabled'], false);
    await rows.first.action!(null);
    expect(calls, 1);
    await rows[1].action!(null);
    expect(calls, 11);
    expect(nativeButtonRows([const Text('An unknown action surface')], prefix: 'voice'), isNull);
    expect(
        nativeButtonRows([
          OmiButton(key: const Key('same'), label: 'One', onPressed: () {}),
          OmiButton(key: const Key('same'), label: 'Two', onPressed: () {}),
        ], prefix: 'voice'),
        isNull);
  });
}
