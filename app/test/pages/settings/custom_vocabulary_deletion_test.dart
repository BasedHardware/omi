import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/custom_vocabulary_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/ui/ui.dart';

const _saveFailed = 'Failed to save. Please check your connection.';

/// Keeps the saved list in memory. A removal answers [saves], as UserProvider does once the server has answered,
/// and a saved removal drops the word and notifies listeners like the real provider.
class _VocabularyUserProvider extends UserProvider {
  _VocabularyUserProvider(List<String> words, {this.saves = true}) : _words = List.of(words);

  final bool saves;
  final List<String> _words;
  final List<String> removeRequests = [];

  @override
  List<String> get transcriptionVocabulary => _words;

  @override
  Future<bool> removeVocabularyWord(String word) async {
    removeRequests.add(word);
    if (!saves) return false;
    _words.remove(word);
    notifyListeners();
    return true;
  }
}

/// Counts the live transcription refreshes the page asks for.
class _CaptureSpy extends ChangeNotifier implements CaptureProvider {
  int settingsChanges = 0;

  @override
  Future<void> onTranscriptionSettingsChanged() async {
    settingsChanges++;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

/// Opens the page on top of another screen, as Settings does. The route has no transitions, so going back
/// disposes the page within the same second the word was tapped.
Future<void> _openPage(WidgetTester tester, UserProvider userProvider, CaptureProvider captureProvider) async {
  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<UserProvider>.value(value: userProvider),
        ChangeNotifierProvider<CaptureProvider>.value(value: captureProvider),
      ],
      child: MaterialApp(
        navigatorKey: globalNavigatorKey,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: const Scaffold(),
      ),
    ),
  );
  globalNavigatorKey.currentState!.push(
    PageRouteBuilder<void>(
      pageBuilder: (context, animation, secondaryAnimation) => const CustomVocabularyPage(),
      transitionDuration: Duration.zero,
      reverseTransitionDuration: Duration.zero,
    ),
  );
  await tester.pumpAndSettle();
}

/// Taps the word's remove button, then goes back before the one-second debounce has sent the removal.
Future<void> _removeAndGoBack(WidgetTester tester, String word) async {
  await tester.tap(find.byTooltip('Remove $word'));
  await tester.pump();
  await tester.tap(find.byType(OmiBackButton));
  await tester.pumpAndSettle();
  expect(find.byType(CustomVocabularyPage), findsNothing);
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('a word removed right before going back is still removed', (tester) async {
    final userProvider = _VocabularyUserProvider(['Omi', 'Callie']);
    final captureProvider = _CaptureSpy();
    addTearDown(userProvider.dispose);
    addTearDown(captureProvider.dispose);
    await _openPage(tester, userProvider, captureProvider);

    await _removeAndGoBack(tester, 'Omi');

    expect(userProvider.removeRequests, ['Omi']);
    expect(userProvider.transcriptionVocabulary, ['Callie']);
    expect(captureProvider.settingsChanges, 1);
    expect(find.text(_saveFailed), findsNothing);
  });

  testWidgets('a removal that fails after going back still shows the error', (tester) async {
    final userProvider = _VocabularyUserProvider(['Omi', 'Callie'], saves: false);
    final captureProvider = _CaptureSpy();
    addTearDown(userProvider.dispose);
    addTearDown(captureProvider.dispose);
    await _openPage(tester, userProvider, captureProvider);

    await _removeAndGoBack(tester, 'Omi');

    expect(userProvider.removeRequests, ['Omi']);
    expect(find.text(_saveFailed), findsOneWidget);
    expect(captureProvider.settingsChanges, 0);
  });

  testWidgets('a word that cannot be removed comes back with an error', (tester) async {
    final userProvider = _VocabularyUserProvider(['Omi', 'Callie'], saves: false);
    final captureProvider = _CaptureSpy();
    addTearDown(userProvider.dispose);
    addTearDown(captureProvider.dispose);
    await _openPage(tester, userProvider, captureProvider);

    await tester.tap(find.byTooltip('Remove Omi'));
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();

    expect(userProvider.removeRequests, ['Omi']);
    expect(find.byTooltip('Remove Omi'), findsOneWidget);
    expect(find.text(_saveFailed), findsOneWidget);
    expect(captureProvider.settingsChanges, 0);
  });

  testWidgets('words removed within a second are sent together while the page stays open', (tester) async {
    final userProvider = _VocabularyUserProvider(['Omi', 'Callie', 'Mixtral']);
    final captureProvider = _CaptureSpy();
    addTearDown(userProvider.dispose);
    addTearDown(captureProvider.dispose);
    await _openPage(tester, userProvider, captureProvider);

    await tester.tap(find.byTooltip('Remove Omi'));
    await tester.pump();
    await tester.tap(find.byTooltip('Remove Callie'));
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();

    expect(userProvider.removeRequests, ['Omi', 'Callie']);
    expect(find.text('Omi'), findsNothing);
    expect(find.text('Mixtral'), findsOneWidget);
    expect(find.text(_saveFailed), findsNothing);
    expect(captureProvider.settingsChanges, 1);
  });
}
