import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/home/firmware_mixin.dart';

void main() {
  test('DFU handoff releases updater before resuming the device exactly once', () async {
    final events = <String>[];
    final handoff = FirmwareDfuConnectionHandoff(
      releaseUpdater: () async => events.add('release updater'),
      resumeDeviceConnection: () async => events.add('resume device'),
    );

    await Future.wait([handoff.finish(), handoff.finish()]);
    await handoff.finish();

    expect(events, ['release updater', 'resume device']);
  });

  test('DFU handoff still resumes the device when updater release fails', () async {
    final events = <String>[];
    final handoff = FirmwareDfuConnectionHandoff(
      releaseUpdater: () async {
        events.add('release updater');
        throw StateError('release failed');
      },
      resumeDeviceConnection: () async => events.add('resume device'),
    );

    await expectLater(handoff.finish(), throwsStateError);

    expect(events, ['release updater', 'resume device']);
  });
}
