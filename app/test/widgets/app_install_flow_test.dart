import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import '../support/test_browser.dart';

class _FakeAppProvider extends AppProvider {
  _FakeAppProvider(this.detail);

  final App detail;

  @override
  Future<App?> getAppDetails(String id) async => detail;
}

App _app({
  bool enabled = false,
  bool external = false,
  bool paid = false,
  String? paymentLink,
  List<AuthStep> authSteps = const [],
  String? setupCompletedUrl,
}) {
  return App(
    id: 'app-1',
    name: 'Notes Sync',
    author: 'Omi',
    description: 'Syncs notes',
    image: '',
    capabilities: {'chat', if (external) 'external_integration'},
    status: 'approved',
    category: 'productivity',
    approved: true,
    ratingCount: 0,
    enabled: enabled,
    deleted: false,
    isPaid: paid,
    isUserPaid: false,
    paymentLink: paymentLink,
    externalIntegration:
        external ? ExternalIntegration(authSteps: authSteps, setupCompletedUrl: setupCompletedUrl) : null,
  );
}

final class _EnvFields implements EnvFields {
  const _EnvFields();

  @override
  String? get apiBaseUrl => 'http://127.0.0.1:9/';

  @override
  String? get googleClientId => null;

  @override
  String? get googleClientSecret => null;

  @override
  String? get intercomAppId => null;

  @override
  String? get intercomIOSApiKey => null;

  @override
  String? get intercomAndroidApiKey => null;

  @override
  String? get posthogApiKey => null;

  @override
  bool? get useAuthCustomToken => false;

  @override
  bool? get useWebAuth => false;
}

void main() {
  late TestBrowser browser;
  setUpAll(() {
    Env.init(const _EnvFields());
    PlatformManager.initializeForLocalHarness();
  });

  setUp(() async {
    browser = TestBrowser();
    browser.install();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  tearDown(() => browser.dispose());

  Future<void> settle(WidgetTester tester) async {
    for (var i = 0; i < 10; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
  }

  Future<void> pumpDetail(
    WidgetTester tester,
    App app, {
    Future<(bool, String)> Function(String)? enableApp,
    Future<Map<String, dynamic>?> Function(String)? appDetailsLoader,
    Future<ApiResult<AppSetupStatus>> Function(String?)? setupChecker,
    Future<App?> Function(String)? detailReader,
    Duration setupProbeTimeout = const Duration(seconds: 20),
  }) async {
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<AppProvider>.value(value: _FakeAppProvider(app)),
          ChangeNotifierProvider<AddAppProvider>.value(value: AddAppProvider()),
          ChangeNotifierProvider<MessageProvider>.value(value: MessageProvider()),
        ],
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: AppDetailPage(
            app: app,
            preventAutoOpenHomePage: true,
            enableApp: enableApp ?? (_) async => (false, ''),
            appDetailsLoader: appDetailsLoader ?? (_) async => null,
            setupChecker: setupChecker ?? (_) async => const ApiSuccess(AppSetupStatus.pending),
            detailReader: detailReader,
            setupProbeTimeout: setupProbeTimeout,
          ),
        ),
      ),
    );
    await tester.pump();
  }

  testWidgets('a failed auto-install after setup shows the backend reason and clears loading', (tester) async {
    var enableCalls = 0;
    var setupChecks = 0;
    final app = _app(
      external: true,
      setupCompletedUrl: 'https://setup.example/done',
      authSteps: [AuthStep(name: 'Connect account', url: 'https://setup.example/connect')],
    );
    await pumpDetail(
      tester,
      app,
      setupChecker: (_) async {
        setupChecks++;
        return const ApiSuccess(AppSetupStatus.completed);
      },
      enableApp: (_) async {
        enableCalls++;
        return (false, 'backend outage reason');
      },
    );
    await settle(tester);

    final state = tester.state<State<AppDetailPage>>(find.byType(AppDetailPage));
    (state as dynamic).checkSetupCompleted(autoInstallIfCompleted: true);
    await settle(tester);

    expect(setupChecks, greaterThanOrEqualTo(2), reason: 'init check plus the auto-install check');
    expect(enableCalls, 1);
    expect(find.text('backend outage reason'), findsOneWidget);
    expect(find.text('Error activating the app'), findsOneWidget);
    expect(app.enabled, isFalse);
    expect(find.text('Enable'), findsOneWidget, reason: 'spinner must release back to the button');
  });

  testWidgets('a confirmed payment that fails install keeps paid state, stops polling, offers Enable', (tester) async {
    var detailReads = 0;
    var enableCalls = 0;
    final app = _app(paid: true, paymentLink: 'https://pay.example/checkout');
    await pumpDetail(
      tester,
      app,
      appDetailsLoader: (_) async {
        detailReads++;
        return {'is_user_paid': true};
      },
      enableApp: (_) async {
        enableCalls++;
        return (false, 'enable failed reason');
      },
    );
    await settle(tester);

    await tester.tap(find.text('Subscribe'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 5));
    await settle(tester);

    expect(detailReads, 1);
    expect(enableCalls, 1);
    expect(app.isUserPaid, isTrue, reason: 'paid state survives the failed install');
    expect(find.text('enable failed reason'), findsOneWidget);
    expect(find.text('Enable'), findsOneWidget);
    expect(find.text('Subscribe'), findsNothing, reason: 'paid state means retry is Enable');

    for (var i = 0; i < 3; i++) {
      await tester.pump(const Duration(seconds: 5));
    }
    expect(detailReads, 1, reason: 'polling stops once payment is confirmed');
  });

  testWidgets('a pending detail read spanning ticks never overlaps requests', (tester) async {
    var detailReads = 0;
    final pending = Completer<Map<String, dynamic>?>();
    var enableCalls = 0;
    final app = _app(paid: true, paymentLink: 'https://pay.example/checkout');
    await pumpDetail(
      tester,
      app,
      appDetailsLoader: (_) {
        detailReads++;
        return pending.future;
      },
      enableApp: (_) async {
        enableCalls++;
        return (true, '');
      },
    );
    await settle(tester);

    await tester.tap(find.text('Subscribe'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 5));
    for (var i = 0; i < 3; i++) {
      await tester.pump(const Duration(seconds: 5));
    }
    expect(detailReads, 1, reason: 'one in-flight read across four ticks');

    pending.complete({'is_user_paid': true});
    await settle(tester);
    expect(app.isUserPaid, isTrue);
    expect(enableCalls, 1);
    expect(app.enabled, isTrue);
  });

  testWidgets('a detail read completing after dispose does not setState', (tester) async {
    final pending = Completer<Map<String, dynamic>?>();
    final app = _app(paid: true, paymentLink: 'https://pay.example/checkout');
    await pumpDetail(tester, app, appDetailsLoader: (_) => pending.future);
    await settle(tester);

    await tester.tap(find.text('Subscribe'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 5));

    await tester.pumpWidget(const SizedBox());
    pending.complete({'is_user_paid': true});
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('a never-finishing detail read stops at the deadline and a late paid result cannot enable',
      (tester) async {
    var detailReads = 0;
    var enableCalls = 0;
    final pending = Completer<Map<String, dynamic>?>();
    final app = _app(paid: true, paymentLink: 'https://pay.example/checkout');
    await pumpDetail(
      tester,
      app,
      appDetailsLoader: (_) {
        detailReads++;
        return pending.future;
      },
      enableApp: (_) async {
        enableCalls++;
        return (true, '');
      },
    );
    await settle(tester);

    await tester.tap(find.text('Subscribe'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 5));
    expect(detailReads, 1);

    for (var i = 0; i < 61; i++) {
      await tester.pump(const Duration(seconds: 5));
    }
    expect(detailReads, 1, reason: 'a hung read counts once; later ticks hit the deadline');
    expect(enableCalls, 0);
    expect(find.text('Subscribe'), findsOneWidget, reason: 'busy state released after the deadline');

    pending.complete({'is_user_paid': true});
    await settle(tester);
    expect(app.isUserPaid, isFalse, reason: 'a stale read cannot mark the app paid');
    expect(enableCalls, 0);
    expect(app.enabled, isFalse);
  });

  testWidgets('a retried poll starts a new read and a stale read cannot steal its in-flight guard', (tester) async {
    final pendingReads = <Completer<Map<String, dynamic>?>>[];
    var enableCalls = 0;
    final app = _app(paid: true, paymentLink: 'https://pay.example/checkout');
    await pumpDetail(
      tester,
      app,
      appDetailsLoader: (_) {
        final read = Completer<Map<String, dynamic>?>();
        pendingReads.add(read);
        return read.future;
      },
      enableApp: (_) async {
        enableCalls++;
        return (true, '');
      },
    );
    await settle(tester);

    await tester.tap(find.text('Subscribe'));
    await tester.pump();
    for (var i = 0; i < 61; i++) {
      await tester.pump(const Duration(seconds: 5));
    }
    expect(pendingReads, hasLength(1));
    expect(enableCalls, 0);

    await tester.tap(find.text('Subscribe'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 5));
    expect(pendingReads, hasLength(2), reason: 'the retry issued a fresh detail read');

    pendingReads[0].complete({'is_user_paid': true});
    await settle(tester);
    expect(app.isUserPaid, isFalse);
    expect(enableCalls, 0, reason: 'the stale read cannot enable after a newer poll started');

    pendingReads[1].complete({'is_user_paid': true});
    await settle(tester);
    expect(app.isUserPaid, isTrue);
    expect(enableCalls, 1);
    expect(app.enabled, isTrue);
  });

  testWidgets('a thrown install error shows the localized fallback and releases the Enable button', (tester) async {
    var enableCalls = 0;
    final app = _app();
    await pumpDetail(
      tester,
      app,
      enableApp: (_) async {
        enableCalls++;
        throw StateError('injected transport failure');
      },
    );
    await settle(tester);

    await tester.tap(find.text('Enable'));
    await settle(tester);

    expect(enableCalls, 1);
    expect(find.text('There was an issue activating this app. Please try again.'), findsOneWidget);
    expect(app.enabled, isFalse);
    expect(find.text('Enable'), findsOneWidget, reason: 'spinner released for retry');
  });

  testWidgets('a missing payment link rejects with the localized error and never calls enable', (tester) async {
    var enableCalls = 0;
    final app = _app(paid: true);
    await pumpDetail(
      tester,
      app,
      enableApp: (_) async {
        enableCalls++;
        return (true, '');
      },
    );
    await settle(tester);

    await tester.tap(find.text('Subscribe'));
    await settle(tester);

    expect(enableCalls, 0, reason: 'missing payment link must not attempt an unpaid install');
    expect(find.text('Invalid payment URL'), findsOneWidget);
  });
  testWidgets('marketplace status can complete after authorization and is installed only once', (tester) async {
    var completed = false;
    var enables = 0;
    final app = _app(
        external: true,
        setupCompletedUrl: 'https://vendor.test/setup',
        authSteps: [AuthStep(name: 'Authorize', url: 'https://vendor.test/auth')]);
    await pumpDetail(tester, app,
        setupChecker: (_) async => ApiSuccess(completed ? AppSetupStatus.completed : AppSetupStatus.pending),
        enableApp: (_) async {
          enables++;
          return (true, '');
        });
    await settle(tester);
    await tester.tap(find.text('Authorize'));
    await settle(tester);
    expect(enables, 0);
    completed = true;
    await tester.pump(const Duration(seconds: 3));
    await settle(tester);
    expect(enables, 1);
    expect(app.enabled, isTrue);
    await tester.pump(const Duration(seconds: 6));
    expect(enables, 1);
  });

  testWidgets('a stuck marketplace probe offers retry and ignores its late reply', (tester) async {
    final pending = Completer<ApiResult<AppSetupStatus>>();
    final app = _app(
        external: true,
        setupCompletedUrl: 'https://vendor.test/setup',
        authSteps: [AuthStep(name: 'Authorize', url: 'https://vendor.test/auth')]);
    await pumpDetail(tester, app, setupProbeTimeout: const Duration(seconds: 1), setupChecker: (_) => pending.future);
    await tester.pump(const Duration(seconds: 2));
    await settle(tester);
    expect(find.byKey(const Key('app-setup-retry')), findsOneWidget);
    pending.complete(const ApiSuccess(AppSetupStatus.completed));
    await settle(tester);
    expect(find.byKey(const Key('app-setup-retry')), findsOneWidget);
    expect(app.enabled, isFalse);
  });

  testWidgets('leaving setup releases its timers and cannot enable from a late response', (tester) async {
    var enables = 0;
    final pending = Completer<ApiResult<AppSetupStatus>>();
    final app = _app(
        external: true,
        setupCompletedUrl: 'https://vendor.test/setup',
        authSteps: [AuthStep(name: 'Authorize', url: 'https://vendor.test/auth')]);
    await pumpDetail(tester, app,
        setupChecker: (_) => pending.future,
        enableApp: (_) async {
          enables++;
          return (true, '');
        });
    await tester.pumpWidget(const SizedBox());
    pending.complete(const ApiSuccess(AppSetupStatus.completed));
    await tester.pump();
    expect(enables, 0);
    expect(tester.takeException(), isNull);
  });

  testWidgets('initial detail failure ends loading, offers retry and drops the expired result', (tester) async {
    final pending = Completer<App?>();
    final app = _app();
    var reads = 0;
    await pumpDetail(tester, app, setupProbeTimeout: const Duration(seconds: 1), detailReader: (_) {
      reads++;
      return reads == 1 ? pending.future : Future.value(app);
    });
    await tester.pump(const Duration(seconds: 2));
    await settle(tester);
    expect(find.byKey(const Key('app-detail-retry')), findsOneWidget);
    await tester.tap(find.byKey(const Key('app-detail-retry')));
    await settle(tester);
    expect(find.byKey(const Key('app-detail-retry')), findsNothing);
    pending.complete(_app(external: true));
    await settle(tester);
    expect(tester.takeException(), isNull);
  });
}
