import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/wals/native_recording_intake.dart';

import '../support/custody_test_helpers.dart';

void main() {
  test('a stale batch directory (moved app container) heals to documents instead of halting intake', () async {
    final documents = await custodyDirectory();
    await SharedPreferencesUtil()
        .saveString('batchAudioDir', '/private/var/mobile/Containers/Data/Application/OLD/Documents');

    final dir = await nativeRecordingDirectory();

    expect(dir.path, documents.path);
    expect(SharedPreferencesUtil().getString('batchAudioDir'), documents.path);
  });

  test('a matching batch directory is used as is', () async {
    final documents = await custodyDirectory();

    expect((await nativeRecordingDirectory()).path, documents.path);
  });
}
