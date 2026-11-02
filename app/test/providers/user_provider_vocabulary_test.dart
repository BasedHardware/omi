import 'package:flutter_test/flutter_test.dart';

import 'package:omi/providers/user_provider.dart';

void main() {
  // Saving sends the whole vocabulary and the server replaces its list with it.
  // Until the list has loaded, the provider only has the cached copy, which is
  // empty after a reinstall or sign-out, so adding a word used to save just
  // that word and drop every saved one.
  group('UserProvider custom vocabulary edits', () {
    test('does not save an added word while the saved list cannot be loaded', () async {
      final saved = <List<String>>[];
      final provider = UserProvider(
        transcriptionPreferencesFetcher: () async => null,
        vocabularySetter: (vocabulary) async {
          saved.add(vocabulary);
          return true;
        },
      );
      addTearDown(provider.dispose);

      expect(await provider.addVocabularyWords(['omi']), isFalse);

      expect(saved, isEmpty);
      expect(provider.transcriptionVocabulary, isEmpty);
      expect(provider.isUpdatingVocabulary, isFalse);
    });

    test('loads the saved list before adding a word, so the saved words are kept', () async {
      Map<String, dynamic>? serverPrefs;
      var fetches = 0;
      final saved = <List<String>>[];
      final provider = UserProvider(
        transcriptionPreferencesFetcher: () async {
          fetches++;
          return serverPrefs;
        },
        vocabularySetter: (vocabulary) async {
          saved.add(vocabulary);
          return true;
        },
      );
      addTearDown(provider.dispose);

      // The list can't be read at first, then the connection comes back.
      expect(await provider.addVocabularyWords(['omi']), isFalse);
      serverPrefs = {
        'vocabulary': ['alpha', 'beta'],
      };
      expect(await provider.addVocabularyWords(['omi']), isTrue);

      expect(saved, [
        ['alpha', 'beta', 'omi'],
      ]);
      expect(provider.transcriptionVocabulary, ['alpha', 'beta', 'omi']);

      // Once loaded, later edits do not read the list again.
      expect(await provider.addVocabularyWords(['gamma']), isTrue);
      expect(saved.last, ['alpha', 'beta', 'omi', 'gamma']);
      expect(fetches, 2);
    });

    test('a batch add saves each distinct word once and ignores blanks', () async {
      Map<String, dynamic>? serverPrefs = {
        'vocabulary': ['alpha'],
      };
      final saved = <List<String>>[];
      final provider = UserProvider(
        transcriptionPreferencesFetcher: () async => serverPrefs,
        vocabularySetter: (vocabulary) async {
          saved.add(vocabulary);
          return true;
        },
      );
      addTearDown(provider.dispose);

      // "omi, omi" typed in one add, plus a blank entry and a word already saved.
      expect(await provider.addVocabularyWords(['omi', 'omi', '', 'alpha']), isTrue);

      expect(saved, [
        ['alpha', 'omi'],
      ]);
      expect(provider.transcriptionVocabulary, ['alpha', 'omi']);
    });

    test('a batch that only repeats existing or blank words saves nothing', () async {
      Map<String, dynamic>? serverPrefs = {
        'vocabulary': ['alpha'],
      };
      final saved = <List<String>>[];
      final provider = UserProvider(
        transcriptionPreferencesFetcher: () async => serverPrefs,
        vocabularySetter: (vocabulary) async {
          saved.add(vocabulary);
          return true;
        },
      );
      addTearDown(provider.dispose);

      expect(await provider.addVocabularyWords(['alpha', '  ']), isFalse);
      expect(saved, isEmpty);
    });

    test('does not save a removal while the saved list cannot be loaded', () async {
      final saved = <List<String>>[];
      final provider = UserProvider(
        transcriptionPreferencesFetcher: () async => null,
        vocabularySetter: (vocabulary) async {
          saved.add(vocabulary);
          return true;
        },
      );
      addTearDown(provider.dispose);

      expect(await provider.removeVocabularyWord('alpha'), isFalse);

      expect(saved, isEmpty);
    });

    test('loads the list again after sign-out before saving', () async {
      Map<String, dynamic>? serverPrefs = {
        'vocabulary': ['alpha'],
      };
      final saved = <List<String>>[];
      final provider = UserProvider(
        transcriptionPreferencesFetcher: () async => serverPrefs,
        vocabularySetter: (vocabulary) async {
          saved.add(vocabulary);
          return true;
        },
      );
      addTearDown(provider.dispose);

      expect(await provider.addVocabularyWords(['omi']), isTrue);
      provider.clearUserData();
      serverPrefs = null;

      expect(await provider.addVocabularyWords(['beta']), isFalse);
      expect(saved, [
        ['alpha', 'omi'],
      ]);
    });
  });
}
