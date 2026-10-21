import 'dart:convert';
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

  test('Watch backups are listed only for the receipt owner, even before their first scan', () async {
    const session = '0123456789abcdef0123456789abcdef';
    const watchName = 'audio_omibatchwatch${session}s0_pcm16_16000_1_fs160_1720000000.bin';
    await File('${dir.path}/$watchName').writeAsBytes([0x40, 1, 0, 0, ...List.filled(320, 0)]);
    await Directory('${dir.path}/.watch-receipts').create();
    await File('${dir.path}/.watch-receipts/$watchName').writeAsString(jsonEncode({
      'metadata': {'version': 1, 'sessionID': session, 'segment': 0, 'startedAt': 1720000000, 'ownerUID': 'user-a'},
      'digest': List.filled(64, 'a').join(),
    }));

    expect(await listFor('user-b'), [recording]);
    expect(await listFor('user-a'), [watchName]);
    expect(File('${dir.path}/$watchName').existsSync(), isTrue);
  });

  test('Watch files awaiting a committed native receipt are never adopted', () async {
    const watchName = 'audio_omibatchwatch0123456789abcdef0123456789abcdefs0_pcm16_16000_1_fs160_1720000000.bin';
    await File('${dir.path}/$watchName').writeAsBytes([0x40, 1, 0, 0, ...List.filled(320, 0)]);
    expect(await listFor('user-a'), [recording]);
    expect(File('${dir.path}/$watchName').existsSync(), isTrue);
  });

  test('corrupt ownership metadata is not treated as unowned recordings', () async {
    expect(await listFor('user-a'), [recording]);
    final owners = File('${dir.path}/omibatch_owners.json');
    final intact = await owners.readAsString();
    await owners.writeAsString(intact.substring(0, intact.length - 3));

    expect(await listFor('user-b'), isEmpty);
    expect(File('${dir.path}/$recording').existsSync(), isTrue);
    expect(await owners.readAsString(), isNot(contains('user-b')));
  });

  test('a non-string owner value fails closed instead of rebinding the file', () async {
    await File('${dir.path}/omibatch_owners.json').writeAsString('{"$recording": 7}');

    expect(await listFor('user-b'), isEmpty);
    expect(File('${dir.path}/$recording').existsSync(), isTrue);
    expect(await File('${dir.path}/omibatch_owners.json').readAsString(), '{"$recording": 7}');
  });

  test('a queued job for another account is not polled', () async {
    expect(await listFor('user-a'), [recording]);
    SharedPreferences.setMockInitialValues({
      'uid': 'user-b',
      'localRecordingJobs': jsonEncode({recording: 'job-a'}),
      'batchAudioDir': dir.path,
    });
    await SharedPreferencesUtil.init();

    final polled = <String>[];
    final provider = LocalRecordingsProvider();
    provider.jobStatusFetcherOverride = (jobId) async {
      polled.add(jobId);
      throw StateError('another account\'s job must not be polled');
    };
    await provider.refresh();
    await provider.reconcileForTesting();

    expect(polled, isEmpty);
    expect(File('${dir.path}/$recording').existsSync(), isTrue);
    provider.dispose();
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
