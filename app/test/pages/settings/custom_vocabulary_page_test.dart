import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/custom_vocabulary_page.dart';
import 'package:omi/providers/user_provider.dart';

const _saveFailed = 'Failed to save. Please check your connection.';

/// Answers every add with false, as UserProvider does when the save fails and
/// when every word is already in the list.
class _RefusingUserProvider extends UserProvider {
  _RefusingUserProvider({this.vocabulary = const []});

  final List<String> vocabulary;
  final List<List<String>> added = [];

  @override
  List<String> get transcriptionVocabulary => vocabulary;

  @override
  Future<bool> addVocabularyWords(List<String> words) async {
    added.add(words);
    return false;
  }
}

Future<void> _addTypedWords(WidgetTester tester, UserProvider provider, String text) async {
  await tester.pumpWidget(
    ChangeNotifierProvider<UserProvider>.value(
      value: provider,
      child: const MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: CustomVocabularyPage(),
      ),
    ),
  );
  await tester.enterText(find.byType(TextField), text);
  await tester.tap(find.byTooltip('Add'));
  await tester.pumpAndSettle();
}

String _fieldText(WidgetTester tester) => tester.widget<TextField>(find.byType(TextField)).controller!.text;

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('a failed save keeps the typed words and shows an error', (tester) async {
    final provider = _RefusingUserProvider();
    addTearDown(provider.dispose);

    await _addTypedWords(tester, provider, 'Omi, Callie');

    expect(provider.added, [
      ['Omi', 'Callie'],
    ]);
    expect(_fieldText(tester), 'Omi, Callie');
    expect(find.text(_saveFailed), findsOneWidget);
  });

  testWidgets('words already in the list clear the field without an error', (tester) async {
    final provider = _RefusingUserProvider(vocabulary: ['Omi', 'Callie']);
    addTearDown(provider.dispose);

    await _addTypedWords(tester, provider, 'Omi, Callie');

    expect(provider.added, [
      ['Omi', 'Callie'],
    ]);
    expect(_fieldText(tester), isEmpty);
    expect(find.text(_saveFailed), findsNothing);
  });
}
