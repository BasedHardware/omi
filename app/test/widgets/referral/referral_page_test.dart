import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api/referrals.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/referral/referral_page.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/utils/platform/platform_manager.dart';

const link = 'https://omi.me/r/ref1.dXNlcg.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';
Widget host(Widget child) => MaterialApp(
      theme: buildOmiTheme(),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: child,
    );

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    OmiClipboard.debugSystemConfirmsCopy = false;
  });

  test('accepts exact referral URLs and rejects foreign or modified URLs', () {
    expect(validateReferralLink(link), link);
    expect(validateReferralLink(link.replaceFirst('omi.me', 'api.omiapi.com')), contains('api.omiapi.com'));
    for (final bad in [
      link.replaceFirst('omi.me', 'evil.example'),
      '$link?x=1',
      '$link#x',
      link.replaceFirst('omi.me', 'omi.me:443'),
      link.replaceFirst('/r/', '/other/'),
      link.replaceFirst('https:', 'http:'),
      link.replaceFirst('omi.me', 'user@omi.me')
    ]) {
      expect(() => validateReferralLink(bad), throwsFormatException);
    }
  });

  testWidgets('default gate never creates a referral session', (tester) async {
    var calls = 0;
    await tester.pumpWidget(host(ReferralPage(createSession: () {
      calls++;
      throw StateError('Must stay dormant');
    })));
    await tester.pump();
    expect(calls, 0);
    expect(find.byKey(const Key('referral-share')), findsNothing);
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(seconds: 20));
  }, skip: mobileReferralCampaignEnabled);

  testWidgets('real URL copy, cancelled share, retry and reentry remain usable', (tester) async {
    var loads = 0;
    var shares = 0;
    String? copied;
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') copied = (call.arguments as Map)['text'] as String;
      return null;
    });
    ReferralPage page() => ReferralPage(
          accountChanges: const Stream.empty(),
          createSession: () => ReferralLinkSession(
              isCurrent: () => true,
              load: () async {
                loads++;
                if (loads == 1) throw StateError('Offline');
                return link;
              }),
          shareLink: (url, origin) async {
            expect(url, link);
            expect(origin.isEmpty, false);
            shares++;
          },
        );
    await tester.pumpWidget(host(page()));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Try Again'));
    await tester.pumpAndSettle();
    for (var i = 0; i < 3; i++) {
      await tester.tap(find.byKey(const Key('referral-copy')));
      await tester.pumpAndSettle();
      expect(copied, link);
      await tester.tap(find.byKey(const Key('referral-share')));
      await tester.pumpAndSettle();
    }
    expect(shares, 3);
    for (var i = 0; i < 3; i++) {
      await tester.pumpWidget(host(const SizedBox()));
      await tester.pumpWidget(host(page()));
      await tester.pumpAndSettle();
      expect(find.text(link), findsOneWidget);
    }
    expect(loads, 5);
  }, skip: !mobileReferralCampaignEnabled);

  testWidgets('share failure recovers and large text remains scrollable', (tester) async {
    var attempts = 0;
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(host(MediaQuery(
      data: const MediaQueryData(textScaler: TextScaler.linear(3.2)),
      child: ReferralPage(
        accountChanges: const Stream.empty(),
        createSession: () => ReferralLinkSession(isCurrent: () => true, load: () async => link),
        shareLink: (_, __) async {
          attempts++;
          if (attempts == 1) throw StateError('Share unavailable');
        },
      ),
    )));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.byKey(const Key('referral-share')), 200);
    await Scrollable.ensureVisible(tester.element(find.byKey(const Key('referral-share'))), alignment: 0.5);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('referral-share')));
    await tester.pumpAndSettle();
    expect(find.text('Something went wrong! Please try again later.'), findsOneWidget);
    await tester.pump(const Duration(seconds: 9));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('referral-share')));
    await tester.pumpAndSettle();
    expect(attempts, 2);
    await tester.scrollUntilVisible(find.byKey(const Key('referral-affiliate')), 200);
    expect(tester.takeException(), isNull);
  }, skip: !mobileReferralCampaignEnabled);

  testWidgets('real synchronous auth broadcast invalidates before settled gateway reload', (tester) async {
    final gateway = _ReferralGateway();
    final auth = AuthService.forTesting(tokenGateway: gateway);
    auth.markAuthenticatedUser('user-a');
    await tester.pumpWidget(host(ReferralPage(
      accountChanges: auth.sessionGenerationEvents.map((_) {}),
      createSession: () {
        final snapshot = auth.captureSessionSnapshot();
        return ReferralLinkSession(
          isCurrent: () => snapshot != null && auth.isSessionSnapshotCurrent(snapshot),
          load: () async {
            if (snapshot == null) throw StateError('Signed out');
            return link;
          },
        );
      },
    )));
    await tester.pumpAndSettle();
    auth.handleAuthUserChanged(null);
    gateway.user = null;
    await tester.pumpAndSettle();
    expect(find.text(link), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
    auth.markAuthenticatedUser('user-b');
    await tester.pump();
    expect(tester.takeException(), isNull);
  }, skip: !mobileReferralCampaignEnabled);

  testWidgets('late account A result cannot replace account B link', (tester) async {
    final changes = StreamController<void>.broadcast(sync: true);
    final old = Completer<String>();
    var generation = 0;
    await tester.pumpWidget(host(ReferralPage(
      accountChanges: changes.stream,
      createSession: () {
        final captured = generation;
        return ReferralLinkSession(
            isCurrent: () => generation == captured, load: () => captured == 0 ? old.future : Future.value('$link-b'));
      },
    )));
    generation = 1;
    changes.add(null);
    await tester.pumpAndSettle();
    old.complete(link);
    await tester.pumpAndSettle();
    expect(find.text(link), findsNothing);
    expect(find.text('$link-b'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    await changes.close();
  }, skip: !mobileReferralCampaignEnabled);
}

final class _ReferralGateway implements AuthTokenGateway {
  AuthUserSnapshot? user = const AuthUserSnapshot(uid: 'user-a');
  @override
  AuthUserSnapshot? get currentUser => user;
  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;
  @override
  Future<void> signOut() async {
    user = null;
  }
}
