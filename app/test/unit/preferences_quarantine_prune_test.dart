import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/preferences_quarantine.dart';

/// Quarantine archives used to accumulate without bound.
///
/// `_quarantine` copies a corrupt value to `<key>.corrupt-<microseconds>` and
/// removes the original. Nothing ever removed the copy, so every corruption
/// event left one behind for good. On iOS these live in NSUserDefaults, which
/// the system reads in full before the first frame.
///
/// Measured on a real device: 13.5 MB across 138 keys, of which a single
/// quarantined `cachedConversations` was 12.5 MB, plus six separate
/// `cachedPeople.corrupt-*` archives. The app took that long to open.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  tearDown(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  String stamp(Duration ago) => '${DateTime.now().subtract(ago).microsecondsSinceEpoch}';

  test('stale quarantine archives are removed at startup', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'cachedPeople.corrupt-${stamp(const Duration(days: 30))}': 'old',
      'cachedPeople.corrupt-${stamp(const Duration(days: 8))}': 'also old',
      'keepMe': 'untouched',
    });
    await SharedPreferencesUtil.init();
    final prefs = await SharedPreferences.getInstance();

    expect(prefs.getKeys().where((k) => k.contains('.corrupt-')), isEmpty,
        reason: 'archives past the retention window must not survive a launch');
    expect(prefs.getString('keepMe'), 'untouched', reason: 'pruning must only touch quarantine archives');
  });

  test('only the newest archive of a key is kept', () async {
    final newest = stamp(const Duration(minutes: 1));
    SharedPreferences.setMockInitialValues(<String, Object>{
      'cachedPeople.corrupt-${stamp(const Duration(hours: 5))}': 'older',
      'cachedPeople.corrupt-${stamp(const Duration(hours: 2))}': 'middle',
      'cachedPeople.corrupt-$newest': 'newest',
    });
    await SharedPreferencesUtil.init();
    final prefs = await SharedPreferences.getInstance();

    final left = prefs.getKeys().where((k) => k.contains('.corrupt-')).toList();
    expect(left, ['cachedPeople.corrupt-$newest'], reason: 'six archives of one key were found on a real device');
    expect(prefs.getString(left.single), 'newest');
  });

  test('a huge corrupt value is dropped rather than archived', () async {
    // The 12.5 MB case: worth recording that it happened, not worth carrying
    // at every launch. It is a cache; the server still has the data.
    final huge = 'x' * (256 * 1024);
    SharedPreferences.setMockInitialValues(<String, Object>{
      'onboardingCompleted': huge, // expected bool -> quarantined on init
    });
    await SharedPreferencesUtil.init();
    final prefs = await SharedPreferences.getInstance();

    expect(prefs.get('onboardingCompleted'), isNot(huge), reason: 'the corrupt original must still be cleared');
    final archives = prefs.getKeys().where((k) => k.contains('.corrupt-'));
    for (final archive in archives) {
      expect((prefs.get(archive) as String).length, lessThan(256 * 1024),
          reason: 'an archive this large is what made the app slow to open');
    }
  });

  test('a small corrupt value is still archived for inspection', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'onboardingCompleted': 'not-a-bool',
    });
    await SharedPreferencesUtil.init();
    final prefs = await SharedPreferences.getInstance();

    final archives = prefs.getKeys().where((k) => k.startsWith('onboardingCompleted.corrupt-')).toList();
    expect(archives, hasLength(1), reason: 'the forensic copy is the whole point of quarantine');
    expect(prefs.get(archives.single), 'not-a-bool');
  });

  test('a copy that cannot be written keeps the previous archive and the original', () async {
    // The previous archive used to be deleted first; a failed write then left none at all.
    SharedPreferences.setMockInitialValues(<String, Object>{
      'cachedPeople': 'still here',
      'cachedPeople.corrupt-${stamp(const Duration(minutes: 5))}': 'previous',
    });
    final prefs = await SharedPreferences.getInstance();
    // A map is not a storable type, so no copy can be written.
    await PreferenceQuarantine.archive(prefs, 'cachedPeople', <String, Object>{'a': 1}, reason: 'test');

    expect(prefs.getString('cachedPeople'), 'still here');
    expect(prefs.getKeys().where((k) => k.startsWith('cachedPeople.corrupt-')).map(prefs.getString), ['previous']);
  });
}
