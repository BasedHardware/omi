import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:cached_network_image/cached_network_image.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/apps/app_detail/widgets/app_preview_gallery.dart';

/// App detail (IMG_1124): a screenshot that does not load drops out instead of a broken "!" tile,
/// and with none left the Preview section is gone.
void main() {
  setUp(() {
    // The image cache needs a directory the test host does not have; keep the download pending so
    // the test decides when an image fails.
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (_) => Completer<Object?>().future,
    );
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), null);
  });

  Future<void> pump(WidgetTester tester, List<String> urls) => tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: AppPreviewGallery(imageUrls: urls)),
      ));

  /// Fails the screenshot at [url] the way a missing file does.
  Future<void> fail(WidgetTester tester, String url) async {
    final image = tester.widget<CachedNetworkImage>(
      find.byWidgetPredicate((w) => w is CachedNetworkImage && w.imageUrl == url),
    );
    image.errorWidget!(tester.element(find.byType(AppPreviewGallery)), url, Exception('404'));
    await tester.pump();
    await tester.pump();
  }

  testWidgets('a screenshot that fails drops out; the others stay', (tester) async {
    await pump(tester, ['https://x.test/a.png', 'https://x.test/b.png']);
    expect(find.byType(CachedNetworkImage), findsNWidgets(2));
    await fail(tester, 'https://x.test/a.png');
    expect(find.byType(CachedNetworkImage), findsOneWidget);
    expect(find.text('Preview'), findsOneWidget);
  });

  testWidgets('with every screenshot failed, the Preview section is gone', (tester) async {
    await pump(tester, ['https://x.test/only.png']);
    expect(find.text('Preview'), findsOneWidget);
    await fail(tester, 'https://x.test/only.png');
    expect(find.text('Preview'), findsNothing);
    expect(find.byType(CachedNetworkImage), findsNothing);
  });
}
