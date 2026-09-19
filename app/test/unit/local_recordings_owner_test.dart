import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/local_recordings_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const recording = 'audio_omibatchphone_opus_fs320_16000_1_fs320_1720000001.bin';
  late Directory dir;

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('local_recordings_owner');
    await File('${dir.path}/$recording').writeAsBytes([4, 0, 0, 0, 1, 2, 3, 4]);
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    await SharedPreferencesUtil().saveString('batchAudioDir', dir.path);
  });

  tearDown(() async {
    if (await dir.exists()) await dir.delete(recursive: true);
  });

  Future<List<String>> listFor(String uid) async {
    SharedPreferencesUtil().uid = uid;
    final provider = LocalRecordingsProvider();
    await provider.refresh();
    final names = provider.recordings.map((r) => r.fileName).toList();
    provider.dispose();
    return names;
  }

  test('a recording made by one account is not listed for the next account', () async {
    expect(await listFor('user-a'), [recording]);

    expect(await listFor('user-b'), isEmpty);
    expect(File('${dir.path}/$recording').existsSync(), isTrue);

    expect(await listFor('user-a'), [recording]);
  });

  test('clearing user data drops the listed recordings', () async {
    SharedPreferencesUtil().uid = 'user-a';
    final provider = LocalRecordingsProvider();
    await provider.refresh();
    expect(provider.recordings, hasLength(1));

    provider.clearUserData();

    expect(provider.recordings, isEmpty);
    provider.dispose();
  });
}
