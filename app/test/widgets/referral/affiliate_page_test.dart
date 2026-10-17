import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/affiliate.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/referral/referral_page.dart';
import 'package:omi/ui/ui.dart';

const _profile = {
  'affiliate_id': '7',
  'name': 'Jane',
  'email': 'jane@example.com',
  'ref_code': 'JANE',
  'coupon': 'JANE10',
  'referral_url': 'https://www.omi.me/?ref=JANE',
};

/// Routes each request to a canned backend reply and records what was sent.
class _Backend {
  _Backend(this.routes);

  final Map<String, (int, Object)> routes;
  final requests = <ApiRequest>[];

  Future<http.Response> send(ApiRequest request) async {
    requests.add(request);
    final path = Uri.parse(request.url).path.split('/v1/affiliate').last;
    final reply = routes['${request.method} $path'];
    if (reply == null) return http.Response('{"detail": "not found"}', 404);
    return http.Response(jsonEncode(reply.$2), reply.$1, headers: {'content-type': 'application/json'});
  }

  AffiliateApi get api => AffiliateApi(send: send);
}

Map<String, (int, Object)> _linkedRoutes() => {
      'GET /me': (200, {'native_enabled': true, 'state': 'linked', 'profile': _profile}),
      'GET /stats': (
        200,
        {
          'total_sales': 1250.0,
          'total_commission': 187.5,
          'total_clicks': 342,
          'total_orders': 9,
          'paid_commission': 120.0,
          'unpaid_commission': 67.5,
        }
      ),
      'GET /orders': (
        200,
        {
          'orders': [
            {'id': '1', 'number': '#1043', 'created_at': '2026-10-12T10:00:00Z', 'commission': 26.0, 'currency': 'USD'},
            {'id': '2', 'number': '#1038', 'created_at': '2026-10-09T10:00:00Z', 'commission': 26.0, 'currency': 'USD'},
          ],
          'count': 9,
        }
      ),
      'GET /earnings': (
        200,
        {
          'commissions': [
            {'commission_type': 'percentage', 'commission_value': 15, 'standard': true},
          ],
          'transactions': [],
        }
      ),
      'GET /payouts/account': (200, {'connected': false, 'has_account': false}),
    };

void main() {
  setUpAll(() async {
    final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List;
    for (final family in manifest) {
      final loader = FontLoader(family['family'] as String);
      for (final font in family['fonts'] as List) {
        loader.addFont(rootBundle.load(font['asset'] as String));
      }
      await loader.load();
    }
    var directory = File(Platform.resolvedExecutable).parent;
    for (var i = 0; i < 8; i++) {
      final fonts = Directory('${directory.path}/material_fonts');
      if (File('${fonts.path}/Roboto-Regular.ttf').existsSync()) {
        for (final family in ['Roboto', 'Ahem']) {
          final loader = FontLoader(family);
          for (final weight in ['Regular', 'Medium', 'Bold']) {
            loader.addFont(
                Future.value(ByteData.sublistView(File('${fonts.path}/Roboto-$weight.ttf').readAsBytesSync())));
          }
          await loader.load();
        }
        break;
      }
      directory = directory.parent;
    }
  });

  setUp(() async {
    Env.overrideApiBaseUrl('https://affiliate.test.invalid/');
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  Future<void> pumpPage(WidgetTester tester, Widget page) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final previousPalette = OmiColors.active;
    OmiColors.active = OmiPalette.dark;
    addTearDown(() => OmiColors.active = previousPalette);
    await tester.pumpWidget(RepaintBoundary(
      key: const Key('affiliate-evidence'),
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: buildOmiTheme().copyWith(platform: TargetPlatform.android),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: page,
      ),
    ));
    await tester.pumpAndSettle();
  }

  // Set OMI_AFFILIATE_EVIDENCE_DIR to write PR screenshots.
  Future<void> evidence(WidgetTester tester, String name) async {
    final path = Platform.environment['OMI_AFFILIATE_EVIDENCE_DIR'];
    if (path == null) return;
    await tester.runAsync(() async {
      final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(const Key('affiliate-evidence')));
      final image = await boundary.toImage(pixelRatio: 2);
      final data = await image.toByteData(format: ui.ImageByteFormat.png);
      await Directory(path).create(recursive: true);
      await File('$path/$name.png').writeAsBytes(data!.buffer.asUint8List());
      image.dispose();
    });
  }

  testWidgets('linked affiliate sees their link, earnings, orders and payout setup', (tester) async {
    final backend = _Backend(_linkedRoutes());
    await pumpPage(tester, ReferralPage(api: backend.api, openUrl: (_) async => true));

    expect(find.text('https://www.omi.me/?ref=JANE'), findsOneWidget);
    expect(find.text('JANE10'), findsOneWidget);
    expect(find.text('You earn 15% on every order'), findsOneWidget);
    expect(find.text(r'$187.50'), findsOneWidget);
    expect(find.text('342'), findsOneWidget);
    await evidence(tester, '001-mobile-android-affiliate-dashboard');

    await tester.scrollUntilVisible(find.text('Set Up Payouts'), 300);
    await tester.pumpAndSettle();
    expect(find.text('#1043'), findsOneWidget);
    await evidence(tester, '002-mobile-android-affiliate-dashboard-lower');
  });

  testWidgets('verified email match links in one tap', (tester) async {
    final routes = _linkedRoutes()
      ..['GET /me'] = (200, {'native_enabled': true, 'state': 'not_linked', 'email_match_available': true})
      ..['POST /link/email'] = (
        200,
        {
          'method': 'email_match',
          'status': {'native_enabled': true, 'state': 'linked', 'profile': _profile},
        }
      );
    final backend = _Backend(routes);
    await pumpPage(tester, ReferralPage(api: backend.api, openUrl: (_) async => true));

    expect(find.text('We found an affiliate account with your email.'), findsOneWidget);
    await evidence(tester, '003-mobile-android-affiliate-email-match');
    await tester.tap(find.byKey(const Key('affiliate-connect-email')));
    await tester.pumpAndSettle();

    expect(
        backend.requests.map((r) => '${r.method} ${Uri.parse(r.url).path}'), contains('POST /v1/affiliate/link/email'));
    expect(find.text('https://www.omi.me/?ref=JANE'), findsOneWidget);
  });

  testWidgets('wrong affiliate password stays in the sheet with a clear error', (tester) async {
    final routes = _linkedRoutes()
      ..['GET /me'] = (200, {'native_enabled': true, 'state': 'not_linked'})
      ..['POST /link/credentials'] = (400, {'detail': 'invalid_credentials'});
    final backend = _Backend(routes);
    await pumpPage(tester, ReferralPage(api: backend.api, openUrl: (_) async => true));

    expect(find.text('Join Program'), findsOneWidget);
    await evidence(tester, '004-mobile-android-affiliate-join');
    await tester.tap(find.byKey(const Key('affiliate-sign-in')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).at(0), 'jane@example.com');
    await tester.enterText(find.byType(TextField).at(1), 'wrong');
    await tester.pump();
    await tester.tap(find.byKey(const Key('affiliate-credentials-submit')));
    await tester.pumpAndSettle();

    expect(find.text("That email and password don't match an affiliate account."), findsOneWidget);
    final sent = backend.requests.last;
    expect(jsonDecode(sent.body), {'email': 'jane@example.com', 'password': 'wrong'});
    await evidence(tester, '005-mobile-android-affiliate-sign-in-error');
  });

  testWidgets('blocked affiliates see why and no data', (tester) async {
    final backend = _Backend({
      'GET /me': (200, {'native_enabled': true, 'state': 'blocked'}),
    });
    await pumpPage(tester, ReferralPage(api: backend.api, openUrl: (_) async => true));
    expect(find.text('Your affiliate account is blocked. Contact support for help.'), findsOneWidget);
    expect(backend.requests, hasLength(1));
  });

  testWidgets('a failed status load offers Try Again instead of the website', (tester) async {
    final backend = _Backend({
      'GET /me': (503, {'detail': 'down'})
    });
    final opened = <String>[];
    await pumpPage(
      tester,
      ReferralPage(
        api: backend.api,
        openUrl: (url) async {
          opened.add(url);
          return true;
        },
      ),
    );
    expect(find.text("Couldn't load your affiliate account."), findsOneWidget);
    expect(find.text('Try Again'), findsOneWidget);
    expect(opened, isEmpty);
  });
}
