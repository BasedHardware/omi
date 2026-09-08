import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/summarized_apps_sheet.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

/// A provider whose two app fetches are held open by completers, so a test can
/// keep the sheet in its "still loading" phase and then release both.
///
/// Overriding the fetches (rather than the caches they fill) is what reproduces
/// the real failure: both production fetches swallow their errors and leave the
/// caches empty, so "the request finished and there is nothing" reaches the
/// widget as exactly the same data as "the request has not finished".
class _GatedConversationDetailProvider extends ConversationDetailProvider {
  final Completer<void> suggestedFetch = Completer<void>();
  final Completer<void> enabledFetch = Completer<void>();

  @override
  Future<void> fetchAndCacheSuggestedApps() => suggestedFetch.future;

  @override
  Future<void> fetchAndCacheEnabledConversationApps() => enabledFetch.future;

  /// Resolves both fetches with nothing to show — a brand new account, whose
  /// enabled and suggested template lists are both legitimately empty.
  void completeFetchesEmpty() {
    suggestedFetch.complete();
    enabledFetch.complete();
  }
}

ServerConversation _conversation() {
  return ServerConversation(
    id: 'conv-1',
    createdAt: DateTime(2026, 7, 1, 9).toUtc(),
    structured: Structured('Sprint sync', 'Short overview.', emoji: '🧠'),
  );
}

_GatedConversationDetailProvider _provider() {
  final conversation = _conversation();
  final provider = _GatedConversationDetailProvider();
  addTearDown(provider.dispose);
  provider.selectedDate = conversationLocalDayKey(conversation.createdAt);
  provider.setCachedConversation(conversation);
  return provider;
}

/// Silences one pre-existing, debug-only framework assertion for the duration
/// of a test.
///
/// `_SheetContainer` paints a black `Container` between the sheet's `ListTile`s
/// and the nearest `Material`, which makes Flutter warn that ink splashes will
/// be hidden. That is existing sheet chrome — it fires wherever this sheet is
/// shown, not because of anything these tests do — but flutter_test turns any
/// framework error into a test failure, which would mask the assertions below.
void _ignoreListTileInkSplashWarning() {
  const message = 'ListTile background color or ink splashes may be invisible';
  final previousOnError = FlutterError.onError;
  FlutterError.onError = (details) {
    if (details.exceptionAsString().contains(message)) return;
    previousOnError?.call(details);
  };
  addTearDown(() => FlutterError.onError = previousOnError);
}

Future<void> _pumpSheet(WidgetTester tester, ConversationDetailProvider provider) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: ThemeData.dark(),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: ChangeNotifierProvider<ConversationDetailProvider>.value(
        value: provider,
        child: const Scaffold(body: SummarizedAppsBottomSheet()),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('shows the skeleton while the template fetches are still in flight', (tester) async {
    final provider = _provider();

    await _pumpSheet(tester, provider);

    expect(find.byType(ShimmerWithTimeout), findsWidgets);
    expect(find.text('Get Creative'), findsNothing);
  });

  testWidgets('replaces the skeleton with the empty state once the fetches return nothing', (tester) async {
    // Regression: `isLoading` was derived from the data alone
    // (`enabledApps.isEmpty && suggestedApps.isEmpty`), so a finished fetch that
    // returned nothing was indistinguishable from one still running and the
    // sheet stayed in `_buildShimmerLoading()` forever. ShimmerWithTimeout only
    // freezes the animation after 5s, so the user was left staring at the same
    // grey placeholder — every account with no installed summary template.
    _ignoreListTileInkSplashWarning();
    final provider = _provider();

    await _pumpSheet(tester, provider);
    expect(find.byType(ShimmerWithTimeout), findsWidgets, reason: 'precondition: the sheet starts out loading');

    provider.completeFetchesEmpty();
    await tester.pump();
    await tester.pump();

    expect(
      find.byType(ShimmerWithTimeout),
      findsNothing,
      reason: 'the fetch is done; an empty result must not read as "still loading"',
    );
    expect(provider.cachedEnabledConversationApps, isEmpty);
    expect(provider.cachedSuggestedApps, isEmpty);
    // The empty state is not blank: the "Get Creative" section is how a user
    // with no templates gets their first one.
    expect(find.text('Get Creative'), findsOneWidget);
    expect(find.text('Create Custom Template'), findsOneWidget);
    expect(find.text('All Templates'), findsOneWidget);
  });
}
