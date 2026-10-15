// Synthetic, offline capture target for the real Review card and shared sheet.
import 'package:flutter/material.dart';
import 'package:marionette_flutter/marionette_flutter.dart';
import 'package:provider/provider.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/review/recent_changes_page.dart';
import 'support/dream_changes_fixture.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/ui/ui.dart';

import 'support/dream_review_context_fixture.dart';

Future<void> main() async {
  MarionetteBinding.ensureInitialized();
  final provider = ReviewProvider(
    isEligible: () => true,
    reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
    loadItems: () async => ApiSuccess(ReviewItemsResponse(items: [dreamSpellingQuestion], remainingToday: 3)),
    sendAnswer: (_, __) async => const ApiSuccess(2),
  );
  await provider.load();
  OmiColors.active = OmiColors.forBrightness(Brightness.dark);
  runApp(ChangeNotifierProvider<ReviewProvider>.value(
    value: provider,
    child: MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: buildOmiTheme(brightness: Brightness.dark),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: RecentChangesPage(
        loadChanges: ({cursor}) async => ApiSuccess(ReviewChangesPage(changes: [dreamSyntheticChange()])),
        setUndone: (id, {required undone}) async => ApiSuccess(dreamSyntheticChange(undone: undone)),
      ),
    ),
  ));
}
