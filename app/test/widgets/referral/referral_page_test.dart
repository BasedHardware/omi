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

const legacyLink = 'https://omi.me/r/ref1.dXNlcg.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';
const link = 'https://omi.me/r/ref2.dXNlcg.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';
const otherLink = 'https://omi.me/r/ref2.b3RoZXI.BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB';
ReferralCampaign campaign({int purchases = 0, int claimed = 0, int claimable = 0, String url = link}) =>
    ReferralCampaign.fromJson({
      'campaign_id': 'omi_pocket_match_v1',
      'enabled': true,
      'referral_url': url,
      'qualified_purchases': purchases,
      'claimed_months': claimed,
      'claimable_months': claimable,
      'reward_status': 'ready'
    });
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
    expect(validateReferralLink(legacyLink), legacyLink);
    expect(validateReferralLink(legacyLink.replaceFirst('omi.me', 'api.omiapi.com')), contains('api.omiapi.com'));
    for (final bad in [
      legacyLink.replaceFirst('omi.me', 'evil.example'),
      '$legacyLink?x=1',
      '$legacyLink#x',
      legacyLink.replaceFirst('omi.me', 'omi.me:443'),
      legacyLink.replaceFirst('/r/', '/other/'),
      legacyLink.replaceFirst('https:', 'http:'),
      legacyLink.replaceFirst('omi.me', 'user@omi.me')
    ]) {
      expect(() => validateReferralLink(bad), throwsFormatException);
    }
  });

  test('campaign snapshot validates typed progress and ref2 URLs', () {
    final json = <String, dynamic>{
      'campaign_id': 'omi_pocket_match_v1',
      'enabled': true,
      'referral_url': link,
      'qualified_purchases': 2,
      'claimed_months': 0,
      'claimable_months': 2,
      'reward_status': 'ready',
      'future_field': true
    };
    expect(ReferralCampaign.fromJson(json).claimableMonths, 2);
    for (final field in [
      'qualified_purchases',
      'claimed_months',
      'claimable_months',
      'milestone_progress',
      'earned_months'
    ]) {
      for (final malformed in ['2', 2.0, null]) {
        expect(() => ReferralCampaign.fromJson({...json, field: malformed}), throwsFormatException);
      }
    }

    for (final bad in [
      legacyLink,
      link.replaceFirst('omi.me', 'evil.example'),
      '$link?x=1',
      '$link#x',
      link.replaceFirst('omi.me', 'omi.me:443'),
      link.replaceFirst('/r/', '/other/'),
      link.replaceFirst('https:', 'http:'),
      link.replaceFirst('omi.me', 'user@omi.me')
    ]) {
      expect(() => validateCampaignReferralLink(bad), throwsFormatException);
    }

    expect(() => ReferralCampaign.fromJson({...json, 'qualified_purchases': 1}), throwsFormatException);
    expect(() => ReferralCampaign.fromJson({...json, 'referral_url': legacyLink}), throwsFormatException);
    expect(() => ReferralCampaign.fromJson({...json, 'enabled': false}), throwsFormatException);
  });

  test('refunded progress preserves lifetime claimed months without new claimability', () {
    for (final pair in [(4, 5), (0, 5), (1, 2)]) {
      final json = <String, dynamic>{
        'campaign_id': 'omi_pocket_match_v1',
        'enabled': true,
        'referral_url': link,
        'qualified_purchases': pair.$1,
        'claimed_months': pair.$2,
        'claimable_months': 0,
        'reward_status': 'active'
      };
      expect(ReferralCampaign.fromJson(json).claimedMonths, pair.$2);
      for (final invalid in [2, 3, 5]) {
        expect(() => ReferralCampaign.fromJson({...json, 'claimable_months': invalid}), throwsFormatException);
      }
    }
  });

  test('server milestones retain consumed friends after refunds and validate additive fields', () {
    final json = <String, dynamic>{
      'campaign_id': 'omi_pocket_match_v1',
      'enabled': true,
      'referral_url': link,
      'qualified_purchases': 4,
      'milestone_progress': 5,
      'earned_months': 5,
      'claimed_months': 2,
      'claimable_months': 3,
      'reward_status': 'active'
    };
    final parsed = ReferralCampaign.fromJson(json);
    expect(parsed.qualifiedPurchases, 4);
    expect(parsed.milestoneProgress, 5);
    expect(parsed.earnedMonths, 5);
    expect(parsed.claimableMonths, 3);
    for (final patch in <Map<String, dynamic>>[
      {'milestone_progress': -1},
      {'milestone_progress': 6},
      {'milestone_progress': 3},
      {'milestone_progress': null},
      {'milestone_progress': 5.0},
      {'earned_months': -1},
      {'earned_months': 3},
      {'earned_months': 6},
      {'earned_months': null},
      {'earned_months': 2},
      {'claimable_months': 0},
      {'claimable_months': 5},
    ]) {
      expect(() => ReferralCampaign.fromJson({...json, ...patch}), throwsFormatException);
    }
    final old = Map<String, dynamic>.from(json)
      ..remove('milestone_progress')
      ..remove('earned_months');
    old['claimable_months'] = 0;
    expect(ReferralCampaign.fromJson(old).milestoneProgress, 4);
    expect(ReferralCampaign.fromJson(old).earnedMonths, 2);
    old['qualified_purchases'] = 0;
    expect(ReferralCampaign.fromJson(old).earnedMonths, 2);
  });

  testWidgets('milestone UI uses consumed progress without changing current purchases', (tester) async {
    final snapshot = ReferralCampaign.fromJson({
      'campaign_id': 'omi_pocket_match_v1',
      'enabled': true,
      'referral_url': link,
      'qualified_purchases': 4,
      'milestone_progress': 5,
      'earned_months': 5,
      'claimed_months': 2,
      'claimable_months': 3,
      'reward_status': 'active'
    });
    await tester.pumpWidget(host(ReferralPage(
        accountChanges: const Stream.empty(),
        createSession: () => ReferralLinkSession(isCurrent: () => true, load: () async => snapshot))));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('referral-reward-5-earned')), findsOneWidget);
    expect(find.text('3/3'), findsNothing);
    expect(find.byKey(const Key('referral-claim')), findsOneWidget);
    expect(snapshot.qualifiedPurchases, 4);
  });

  testWidgets('claim uses server result, duplicates do not add months, reentry persists', (tester) async {
    var stored = campaign(purchases: 2, claimable: 2);
    var claims = 0;
    ReferralPage page() => ReferralPage(
        accountChanges: const Stream.empty(),
        createSession: () => ReferralLinkSession(
            isCurrent: () => true,
            load: () async => stored,
            claim: () async {
              claims++;
              return stored = campaign(purchases: 2, claimed: 2);
            }));
    await tester.pumpWidget(host(page()));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('referral-claim')));
    await tester.tap(find.byKey(const Key('referral-claim')));
    await tester.pumpAndSettle();
    expect(claims, 1);
    expect(find.byKey(const Key('referral-claim')), findsNothing);
    expect(find.text('2/2'), findsOneWidget);
    for (var i = 0; i < 3; i++) {
      await tester.pumpWidget(host(const SizedBox()));
      await tester.pumpWidget(host(page()));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('referral-reward-2-earned')), findsOneWidget);
      expect(find.byKey(const Key('referral-claim')), findsNothing);
      expect(claims, 1);
    }
  });

  testWidgets('claim failure retains progress and retry accepts only server totals', (tester) async {
    var attempts = 0;
    await tester.pumpWidget(host(ReferralPage(
        accountChanges: const Stream.empty(),
        createSession: () => ReferralLinkSession(
            isCurrent: () => true,
            load: () async => campaign(purchases: 5, claimed: 2, claimable: 3),
            claim: () async {
              if (++attempts == 1) throw StateError('Offline');
              return campaign(purchases: 5, claimed: 5);
            }))));
    await tester.pumpAndSettle();
    for (var i = 0; i < 2; i++) {
      await Scrollable.ensureVisible(tester.element(find.byKey(const Key('referral-claim'))), alignment: 0.5);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('referral-claim')));
      await tester.pumpAndSettle();
      if (i == 0) {
        expect(find.byKey(const Key('referral-claim')), findsOneWidget);
        await tester.pump(const Duration(seconds: 9));
      }
    }
    expect(find.byKey(const Key('referral-reward-5-earned')), findsOneWidget);
    expect(find.byKey(const Key('referral-claim')), findsNothing);
    expect(attempts, 2);
  });

  testWidgets('late claim cannot expose prior account rewards', (tester) async {
    final changes = StreamController<void>.broadcast(sync: true);
    final pending = Completer<ReferralCampaign>();
    var generation = 0;
    await tester.pumpWidget(host(ReferralPage(
        accountChanges: changes.stream,
        createSession: () {
          final owner = generation;
          return ReferralLinkSession(
              isCurrent: () => owner == generation,
              load: () async => owner == 0 ? campaign(purchases: 2, claimable: 2) : campaign(),
              claim: () => pending.future);
        })));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('referral-claim')));
    await tester.tap(find.byKey(const Key('referral-claim')));
    await tester.pump();
    generation++;
    changes.add(null);
    await tester.pump();
    pending.complete(campaign(purchases: 2, claimed: 2));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('referral-reward-2-earned')), findsNothing);
    expect(find.text('0/2'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    await changes.close();
  });

  testWidgets('async disabled campaign keeps browser fallback across three resumes', (tester) async {
    var launches = 0;
    const browserChannel = MethodChannel('plugins.flutter.io/url_launcher');
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(browserChannel, (call) async {
      expect(call.method, 'launch');
      expect((call.arguments as Map)['url'], 'https://affiliate.omi.me/');
      launches++;
      return true;
    });
    addTearDown(() => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(browserChannel, null));
    var loads = 0;
    await tester.pumpWidget(host(ReferralPage(
        accountChanges: const Stream.empty(),
        createSession: () => ReferralLinkSession(
            isCurrent: () => true,
            load: () async {
              loads++;
              await Future<void>.delayed(const Duration(milliseconds: 100));
              return ReferralCampaign.fromJson({
                'campaign_id': 'omi_pocket_match_v1',
                'enabled': false,
                'referral_url': null,
                'qualified_purchases': 0,
                'claimed_months': 0,
                'claimable_months': 0,
                'reward_status': 'disabled'
              });
            }))));
    await tester.pumpAndSettle();
    expect(launches, 1);
    for (var i = 0; i < 3; i++) {
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 150));
      await tester.pumpAndSettle();
      expect(launches, 1);
      expect(loads, 1);
      for (final key in ['referral-share', 'referral-copy', 'referral-claim']) {
        expect(find.byKey(Key(key)), findsNothing);
      }
    }
    await tester.tap(find.byKey(const Key('referral-open-browser')));
    await tester.pumpAndSettle();
    expect(launches, 2);
  });

  testWidgets('old backend 404 or error shows the affiliate page and resumes never reopen it', (tester) async {
    var launches = 0;
    const browserChannel = MethodChannel('plugins.flutter.io/url_launcher');
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(browserChannel, (call) async {
      expect((call.arguments as Map)['url'], 'https://affiliate.omi.me/');
      launches++;
      return true;
    });
    addTearDown(() => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(browserChannel, null));
    var loads = 0;
    await tester.pumpWidget(host(ReferralPage(
        accountChanges: const Stream.empty(),
        createSession: () => ReferralLinkSession(
            isCurrent: () => true,
            load: () async {
              loads++;
              throw StateError('Referral campaign unavailable'); // getReferralCampaign on HTTP 404
            }))));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('referral-open-browser')), findsOneWidget);
    expect(launches, 1);
    for (var i = 0; i < 3; i++) {
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpAndSettle();
      expect(loads, 1);
      expect(launches, 1);
      for (final key in ['referral-share', 'referral-copy', 'referral-claim']) {
        expect(find.byKey(Key(key)), findsNothing);
      }
    }
  });

  test('short link shows host and path without the signed token', () {
    expect(referralShortLink(link), 'omi.me/r/…AAAAAA');
    expect(referralShortLink(link).length, lessThan(20));
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
                return campaign();
              }),
          shareLink: (url, origin) async {
            expect(url, link);
            expect(origin.isEmpty, false);
            shares++;
          },
        );
    const browserChannel = MethodChannel('plugins.flutter.io/url_launcher');
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(browserChannel, (call) async => true);
    addTearDown(() => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(browserChannel, null));
    await tester.pumpWidget(host(page()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('referral-open-browser')), findsOneWidget);
    await tester.pumpWidget(host(const SizedBox()));
    await tester.pumpWidget(host(page()));
    await tester.pumpAndSettle();
    expect(find.text(referralShortLink(link)), findsOneWidget);
    expect(find.text(link), findsNothing);
    for (var i = 0; i < 3; i++) {
      await Scrollable.ensureVisible(tester.element(find.byKey(const Key('referral-copy'))), alignment: 0.5);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('referral-copy')));
      await tester.pumpAndSettle();
      expect(copied, link);
      await Scrollable.ensureVisible(tester.element(find.byKey(const Key('referral-share'))), alignment: 0.5);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('referral-share')));
      await tester.pumpAndSettle();
    }
    expect(shares, 3);
    for (var i = 0; i < 3; i++) {
      await tester.pumpWidget(host(const SizedBox()));
      await tester.pumpWidget(host(page()));
      await tester.pumpAndSettle();
      expect(find.text(referralShortLink(link)), findsOneWidget);
    }
    expect(loads, 5);
  });

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
        createSession: () => ReferralLinkSession(isCurrent: () => true, load: () async => campaign()),
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
  });

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
            return campaign();
          },
        );
      },
    )));
    await tester.pumpAndSettle();
    auth.handleAuthUserChanged(null);
    gateway.user = null;
    await tester.pumpAndSettle();
    expect(find.text(referralShortLink(link)), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
    auth.markAuthenticatedUser('user-b');
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('late account A result cannot replace account B link', (tester) async {
    final changes = StreamController<void>.broadcast(sync: true);
    final old = Completer<ReferralCampaign>();
    var generation = 0;
    await tester.pumpWidget(host(ReferralPage(
      accountChanges: changes.stream,
      createSession: () {
        final captured = generation;
        return ReferralLinkSession(
            isCurrent: () => generation == captured,
            load: () => captured == 0 ? old.future : Future.value(campaign(url: otherLink)));
      },
    )));
    generation = 1;
    changes.add(null);
    await tester.pumpAndSettle();
    old.complete(campaign());
    await tester.pumpAndSettle();
    expect(find.text(referralShortLink(link)), findsNothing);
    expect(find.text(referralShortLink(otherLink)), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    await changes.close();
  });
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
