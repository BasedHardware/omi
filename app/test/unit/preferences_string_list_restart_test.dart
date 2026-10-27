import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';

/// After a restart, the platform channel hands every stored string list back as `List<Object?>`
/// (StandardMessageCodec has no typed lists), and `SharedPreferences.get` returns it unconverted.
/// `setMockInitialValues` with an `<Object?>` list reproduces exactly what a real device loads.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Iterable<String> archives(SharedPreferences prefs) => prefs.getKeys().where((k) => k.contains('.corrupt-'));

  test('a string list saved before a restart is read back, not quarantined as a type mismatch', () async {
    SharedPreferences.setMockInitialValues({
      'cachedTranscriptionVocabulary': <Object?>['Omi', 'Tailscale'],
    });
    await SharedPreferencesUtil.init();

    expect(SharedPreferencesUtil().getStringList('cachedTranscriptionVocabulary'), ['Omi', 'Tailscale']);

    // The quarantine runs unawaited; give it the chance to have run.
    await Future<void>.delayed(Duration.zero);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getStringList('cachedTranscriptionVocabulary'), ['Omi', 'Tailscale'],
        reason: 'the saved list was deleted on read');
    expect(archives(prefs), isEmpty, reason: 'a valid list was archived as corrupt');
  });

  test('a stored list that holds a non-string is still quarantined', () async {
    SharedPreferences.setMockInitialValues({
      'cachedTranscriptionVocabulary': <Object?>['Omi', 42],
    });
    await SharedPreferencesUtil.init();

    expect(SharedPreferencesUtil().getStringList('cachedTranscriptionVocabulary'), isEmpty);
    await Future<void>.delayed(Duration.zero);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.containsKey('cachedTranscriptionVocabulary'), isFalse);
    expect(archives(prefs), hasLength(1));
  });

  test('legacy pending uploads loaded at startup survive the boot schema check', () async {
    // flash_page_pending_uploads is the pre-WAL Limitless upload queue that
    // WalFileManager.migrateLegacyLimitlessFiles reads after init. Archived at boot, those
    // recordings would never be migrated.
    SharedPreferences.setMockInitialValues({
      'flash_page_pending_uploads': <Object?>['/docs/audio_limitless_1.bin'],
    });
    await SharedPreferencesUtil.init();

    final prefs = await SharedPreferences.getInstance();
    expect(archives(prefs), isEmpty);
    expect(SharedPreferencesUtil().getStringList('flash_page_pending_uploads'), ['/docs/audio_limitless_1.bin']);
  });
}
