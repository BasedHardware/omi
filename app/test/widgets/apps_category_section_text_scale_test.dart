import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/widgets/category_section.dart';
import 'package:omi/providers/app_provider.dart';

import '../support/real_fonts.dart';

class _Categories extends ChangeNotifier implements AddAppProvider {
  @override
  List<Category> get categories => [];

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Apps extends ChangeNotifier implements AppProvider {
  @override
  List<App> get apps => [];

  @override
  List<bool> get appLoading => [];

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

App _app(int i) => App.fromJson({
      'id': 'app_$i',
      'name': 'Meeting Notes $i',
      'author': 'Omi',
      'description': 'Notes from every meeting',
      'image': '',
      'category': 'productivity-and-organization',
      'capabilities': ['memories'],
      'rating_avg': 4.6,
      'rating_count': 120,
      'enabled': false,
    });

void main() {
  setUpAll(loadRealFonts);

  // #19238: rows were a fixed 85 pt and the title band 60 pt, so a card's name, category and
  // rating overflowed at larger text; they now follow the text size.
  for (final scale in [1.0, 1.15, 1.3, 1.5]) {
    testWidgets('three rows of apps fit at ${scale}x text', (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final errors = <String>[];
      final previous = FlutterError.onError;
      FlutterError.onError = (details) => errors.add(details.exceptionAsString().split('\n').first);
      addTearDown(() => FlutterError.onError = previous);

      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider<AddAppProvider>(create: (_) => _Categories()),
            ChangeNotifierProvider<AppProvider>(create: (_) => _Apps()),
          ],
          child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            builder: (context, child) =>
                MediaQuery(data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(scale)), child: child!),
            home: Scaffold(
              body: SingleChildScrollView(
                child:
                    CategorySection(categoryName: 'Productivity', apps: [_app(1), _app(2), _app(3)], onViewAll: () {}),
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      FlutterError.onError = previous;

      expect(errors.where((e) => e.contains('overflowed')), isEmpty);
      expect(find.text('Meeting Notes 1'), findsOneWidget);
    });
  }
}
