import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/wal_file_manager.dart';

class _Documents extends PathProviderPlatform {
  _Documents(this.path);
  final String path;
  @override
  Future<String> getApplicationDocumentsPath() async => path;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory directory;
  late PathProviderPlatform previousProvider;
  setUp(() async {
    directory = await Directory.systemTemp.createTemp('upgrade-boot-');
    previousProvider = PathProviderPlatform.instance;
    PathProviderPlatform.instance = _Documents(directory.path);
  });
  tearDown(() async {
    PathProviderPlatform.instance = previousProvider;
    await directory.delete(recursive: true);
  });

  test('old and corrupt boot preferences quarantine originals and load defaults', () async {
    SharedPreferences.setMockInitialValues({
      'onboardingCompleted': 'yes',
      'batchModeEnabled': 3,
      'deviceIdHash': 42,
      'appearanceMode': true,
      'authTokenSecureMigrated': 'old',
      'btDevice': '{"id":42}',
      'btDevices': ['{"id":"old-pairing","type":0}', 'not-json'],
      'capturePolicy': '{"version":99,"revision":1,"muted":false}',
    });
    await SharedPreferencesUtil.init();
    final prefs = SharedPreferencesUtil();
    expect(prefs.onboardingCompleted, isFalse);
    expect(prefs.batchModeEnabled, isFalse);
    expect(prefs.btDevice.id, isEmpty);
    expect(prefs.btDevices, isEmpty);
    expect(prefs.deviceIdHash, isEmpty);
    expect(prefs.appearanceMode, 'system');
    final stored = await SharedPreferences.getInstance();
    await Future<void>.delayed(const Duration(milliseconds: 10));
    for (final key in ['onboardingCompleted', 'batchModeEnabled', 'btDevice', 'btDevices', 'capturePolicy']) {
      expect(stored.getKeys().any((candidate) => candidate.startsWith('$key.corrupt-')), isTrue);
    }
    final archivedPairing = stored.getKeys().singleWhere((key) => key.startsWith('btDevice.corrupt-'));
    expect(stored.getString(archivedPairing), '{"id":42}');
    expect(await File('${directory.path}/boot_stages.json').readAsString(), contains('quarantine:btDevice'));
  });

  test('mixed-type list is archived as JSON before the original is removed', () async {
    const key = 'flash_page_pending_uploads';
    SharedPreferences.setMockInitialValues({
      key: <dynamic>['upload-1', 42]
    });
    await SharedPreferencesUtil.init();
    final stored = await SharedPreferences.getInstance();
    expect(stored.containsKey(key), isFalse);
    final archive = stored.getKeys().singleWhere((candidate) => candidate.startsWith('$key.corrupt-'));
    expect(jsonDecode(stored.getString(archive)!), ['upload-1', 42]);
    expect(SharedPreferencesUtil().getStringList(key), isEmpty);
    final journal = jsonDecode(await File('${directory.path}/boot_stages.json').readAsString()) as List<dynamic>;
    expect(
        journal,
        contains(predicate<Map<String, dynamic>>(
          (entry) => entry['stage'] == 'quarantine:$key' && entry['state'] == 'invalid_schema',
        )));
  });

  test('pre-fencing WAL index admits valid old entries and archives a corrupt sibling', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    final index = File('${directory.path}/wals.json');
    await index.writeAsString(jsonEncode({
      'wals': [
        {'timer_start': 1000, 'codec': 'BleAudioCodec.opus', 'seconds': 30},
        {'timer_start': 'old-string', 'codec': 'BleAudioCodec.opus'},
      ],
    }));
    await WalFileManager.init();
    final loaded = await WalFileManager.loadWals();
    expect(loaded.length, 1);
    expect(loaded.single.timerStart, 1000);
    expect(loaded.single.ownerUid, isNull);
    expect(directory.listSync().whereType<File>().any((file) => file.path.contains('wals.json.corrupt-')), isTrue);
    final archived =
        directory.listSync().whereType<File>().singleWhere((file) => file.path.contains('wals.json.corrupt-'));
    expect(await archived.readAsString(), contains('old-string'));
    expect(await WalFileManager.loadWals(), hasLength(1));
  });

  test('pre-upgrade paired device payload remains readable', () async {
    SharedPreferences.setMockInitialValues({
      'btDevice': '{"id":"old-pairing","name":"Omi","type":0,"rssi":"-40"}',
      'btDevices': ['{"id":"old-pairing","name":"Omi","type":0,"rssi":"-40"}'],
    });
    await SharedPreferencesUtil.init();
    expect(SharedPreferencesUtil().btDevice.id, 'old-pairing');
    expect(SharedPreferencesUtil().btDevices.single.rssi, -40);
  });

  test('invalid WAL index falls back to backup without throwing or deleting audio', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    await File('${directory.path}/wals.json').writeAsString('{invalid');
    await File('${directory.path}/wals_backup.json').writeAsString(jsonEncode({
      'wals': [
        {'timer_start': 2000, 'codec': 'BleAudioCodec.opus'},
      ],
    }));
    final audio = File('${directory.path}/audio_old.bin');
    await audio.writeAsBytes([1, 2, 3]);
    await WalFileManager.init();
    expect((await WalFileManager.loadWals()).single.timerStart, 2000);
    expect(await audio.readAsBytes(), [1, 2, 3]);
    expect(directory.listSync().whereType<File>().any((file) => file.path.contains('wals.json.corrupt-')), isTrue);
  });
}
