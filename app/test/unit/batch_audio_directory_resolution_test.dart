import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/batch_recording.dart';

class _FakePathProviderPlatform extends PathProviderPlatform {
  final Directory docsDir;
  _FakePathProviderPlatform(this.docsDir);

  @override
  Future<String?> getApplicationDocumentsPath() async => docsDir.path;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('resolveBatchAudioDirectoryPath — pure precedence', () {
    test('returns customDir when provided and non-empty', () {
      final resolved = resolveBatchAudioDirectoryPath(
        customDir: '/storage/emulated/0/Music/Omi',
        configuredDir: '/data/user/0/com.friend.ios/app_flutter',
        defaultDocsDir: '/data/user/0/com.friend.ios/app_flutter',
      );
      expect(resolved, '/storage/emulated/0/Music/Omi');
    });

    test('trims whitespace and ignores blank customDir', () {
      final resolved = resolveBatchAudioDirectoryPath(
        customDir: '   ',
        configuredDir: '/custom/configured',
        defaultDocsDir: '/default/docs',
      );
      expect(resolved, '/custom/configured');
    });

    test('falls back to defaultDocsDir when both custom and configured are blank', () {
      final resolved = resolveBatchAudioDirectoryPath(
        customDir: '',
        configuredDir: null,
        defaultDocsDir: '/default/docs',
      );
      expect(resolved, '/default/docs');
    });
  });

  group('resolveEffectiveBatchAudioDirectory & Wal.getFilePath with filesystem', () {
    late Directory tempRoot;
    late Directory defaultDocsDir;
    late Directory customAudioDir;

    setUp(() async {
      tempRoot = await Directory.systemTemp.createTemp('audio_storage_test');
      defaultDocsDir = Directory('${tempRoot.path}/docs')..createSync(recursive: true);
      customAudioDir = Directory('${tempRoot.path}/custom_omi')..createSync(recursive: true);

      PathProviderPlatform.instance = _FakePathProviderPlatform(defaultDocsDir);
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
    });

    tearDown(() async {
      if (tempRoot.existsSync()) {
        await tempRoot.delete(recursive: true);
      }
    });

    test('resolveEffectiveBatchAudioDirectory returns custom when exists', () async {
      SharedPreferencesUtil().customAudioStorageDir = customAudioDir.path;
      final effective = await resolveEffectiveBatchAudioDirectory();
      expect(effective.path, customAudioDir.path);
    });

    test('resolveEffectiveBatchAudioDirectory falls back to docs when custom dir does not exist', () async {
      SharedPreferencesUtil().customAudioStorageDir = '${tempRoot.path}/non_existent_folder';
      final effective = await resolveEffectiveBatchAudioDirectory();
      expect(effective.path, defaultDocsDir.path);
    });

    test('setCustomAudioStorageDirectory updates preference and synchronizes batchAudioDir', () async {
      final newDir = Directory('${tempRoot.path}/new_audio_dir');
      expect(newDir.existsSync(), isFalse);

      final result = await setCustomAudioStorageDirectory(newDir.path);
      expect(result.path, newDir.path);
      expect(newDir.existsSync(), isTrue);
      expect(SharedPreferencesUtil().customAudioStorageDir, newDir.path);
      expect(SharedPreferencesUtil().getString('batchAudioDir'), newDir.path);
    });

    test('setCustomAudioStorageDirectory empty resets to defaultDocsDir', () async {
      await setCustomAudioStorageDirectory(customAudioDir.path);
      expect(SharedPreferencesUtil().customAudioStorageDir, customAudioDir.path);
      expect(SharedPreferencesUtil().getString('batchAudioDir'), customAudioDir.path);

      final resetResult = await setCustomAudioStorageDirectory('');
      expect(resetResult.path, defaultDocsDir.path);
      expect(SharedPreferencesUtil().customAudioStorageDir, isEmpty);
      expect(SharedPreferencesUtil().getString('batchAudioDir'), defaultDocsDir.path);
    });

    test('LocalRecordingsProvider scans recordings from customAudioStorageDir', () async {
      await setCustomAudioStorageDirectory(customAudioDir.path);
      SharedPreferencesUtil().uid = 'user-test-123';

      const recordingName = 'audio_omibatchphone_opus_fs320_16000_1_fs320_1720000002.bin';
      await File('${customAudioDir.path}/$recordingName').writeAsBytes([4, 0, 0, 0, 1, 2, 3, 4]);

      final provider = LocalRecordingsProvider();
      await provider.refresh();

      expect(provider.recordings.map((r) => r.fileName), contains(recordingName));
      provider.dispose();
    });

    test('Wal.getFilePath resolves file in customAudioStorageDir', () async {
      SharedPreferencesUtil().customAudioStorageDir = customAudioDir.path;
      const fileName = 'audio_omibatch_test_123.bin';
      final fileInCustom = File('${customAudioDir.path}/$fileName')..writeAsStringSync('dummy');

      final resolvedPath = await Wal.getFilePath(fileName);
      expect(resolvedPath, fileInCustom.path);
    });

    test('Wal.getFilePath falls back to defaultDocsDir when not in custom', () async {
      SharedPreferencesUtil().customAudioStorageDir = customAudioDir.path;
      const fileName = 'audio_legacy_in_docs.bin';
      final fileInDocs = File('${defaultDocsDir.path}/$fileName')..writeAsStringSync('dummy');

      final resolvedPath = await Wal.getFilePath(fileName);
      expect(resolvedPath, fileInDocs.path);
    });
  });
}
