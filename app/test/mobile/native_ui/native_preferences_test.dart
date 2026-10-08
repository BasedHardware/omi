import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/assistant_voices.dart';
import 'package:omi/backend/http/api/wrapped.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/gen/siri_pigeon.g.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_home.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/pages/onboarding/guided_voice_controller.dart';
import 'package:omi/pages/settings/conversation_timeout_dialog.dart';
import 'package:omi/pages/settings/settings_destinations.dart';
import 'package:omi/pages/settings/data_privacy_page.dart';
import 'package:omi/pages/settings/transcription/json_editor_page.dart';
import 'package:omi/pages/settings/transcription/transcription_dialogs.dart';
import 'package:omi/pages/settings/voice_settings_page.dart';
import 'package:omi/pages/settings/wrapped_2025_page.dart';
import 'package:omi/pages/settings/wrapped_2025_share_templates.dart' as templates;
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/siri_integration.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../../providers/guided_voice_controller_test.dart' show FakeVoiceIO;
import 'native_test_host.dart';

const _config = MethodChannel('com.omi.native_ui/config');
final _l10n = lookupAppLocalizations(const Locale('en'));

TestDefaultBinaryMessenger get _messenger => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

/// The latest snapshot published to the most recently created native view.
Map _snapshot(NativeTestHost host) =>
    host.calls.lastWhere((call) => call.$1 == host.created.last && call.$2.method == 'update').$2.arguments as Map;

/// Every row of [snapshot] by id: toolbar first, then section rows.
Map<String, Map> _rows(Map snapshot) => {
      for (final row in (snapshot['toolbar'] as List).cast<Map>()) row['id'] as String: row,
      for (final section in (snapshot['sections'] as List).cast<Map>())
        for (final row in (section['rows'] as List).cast<Map>()) row['id'] as String: row,
    };

List<String> _sectionIds(Map snapshot) =>
    [for (final section in (snapshot['sections'] as List).cast<Map>()) section['id'] as String];

/// Sends a native row command to the most recent view; the reply envelope's error code, or null.
Future<String?> _send(NativeTestHost host, String id, [Object? value]) async {
  final reply = await host.sendFromNative(host.created.last, MethodCall('action', {'id': id, 'value': value}));
  try {
    const StandardMethodCodec().decodeEnvelope(reply!);
    return null;
  } on PlatformException catch (error) {
    return error.code;
  }
}

/// Answers the config channel: 'capabilities' with [capabilities] and 'present' through [present].
List<Map> _answerConfig({List<String> capabilities = const [], Object? Function(Map snapshot)? present}) {
  final presented = <Map>[];
  _messenger.setMockMethodCallHandler(_config, (call) async {
    if (call.method == 'capabilities') return capabilities;
    if (call.method != 'present' || present == null) return null;
    final snapshot = (call.arguments as Map)['snapshot'] as Map;
    presented.add(snapshot);
    final reply = present(snapshot);
    if (reply is Exception) throw reply;
    return reply;
  });
  addTearDown(() => _messenger.setMockMethodCallHandler(_config, null));
  return presented;
}

class _TestEnvFields implements EnvFields {
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => 'http://127.0.0.1:1/';
  @override
  String? get intercomAppId => null;
  @override
  String? get intercomIOSApiKey => null;
  @override
  String? get intercomAndroidApiKey => null;
  @override
  String? get googleClientId => null;
  @override
  String? get googleClientSecret => null;
  @override
  bool? get useWebAuth => false;
  @override
  bool? get useAuthCustomToken => false;
}

void main() {
  setUpAll(() {
    try {
      Env.init(_TestEnvFields());
    } catch (_) {}
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'uid-a'});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    debugResetNativeUiCapabilities();
  });

  group('Data & Privacy Shortcuts', () {
    Future<NativeTestHost> pumpPrivacy(WidgetTester tester,
        {required bool shortcutsAvailable, required List<String> capabilities}) async {
      final host = NativeTestHost.install();
      _answerConfig(capabilities: capabilities);
      SiriIntegration.testInstance = SiriIntegration.forTest(_SiriHost(shortcutsAvailable), 'uid-a');
      DataPrivacyPage.debugPlatformForTest = (ios: true, shortcutsHint: true, searchHint: false);
      addTearDown(() {
        SiriIntegration.testInstance = null;
        DataPrivacyPage.debugPlatformForTest = null;
      });
      final apps = AppProvider();
      addTearDown(apps.dispose);
      await tester.pumpWidget(MultiProvider(providers: [
        ChangeNotifierProvider<UserProvider>(create: (_) => UserProvider()),
        ChangeNotifierProvider<AppProvider>.value(value: apps),
      ], child: NativeTestHost.app(const DataPrivacyPage())));
      await NativeTestHost.settle(tester);
      return host;
    }

    Finder surfaceView() =>
        find.byWidgetPredicate((widget) => widget is UiKitView && widget.viewType == 'com.omi.native_ui/surface');
    Finder shortcutsButton() =>
        find.byWidgetPredicate((widget) => widget is UiKitView && widget.viewType == 'omi/shortcuts_button');

    testWidgets('the native list carries the ShortcutsLink only when both gates hold', (tester) async {
      final host = await pumpPrivacy(tester, shortcutsAvailable: true, capabilities: ['shortcuts_link']);

      expect(surfaceView(), findsOneWidget);
      expect(shortcutsButton(), findsNothing);
      final snapshot = _snapshot(host);
      expect(_sectionIds(snapshot), containsAllInOrder(['siri', 'siri_shortcuts']));
      final rows = _rows(snapshot);
      expect(rows['siri_shortcuts_link']!['kind'], 'shortcuts_link');
      expect(rows['siri_shortcuts_link']!['enabled'], false);
      expect(rows['siri_shortcuts_hint']!['title'], _l10n.askOmi);
      expect(rows['siri_shortcuts_hint']!['subtitle'], _l10n.siriShortcutsSetupHint('Ask Omi', 'Question for Omi'));
    });

    testWidgets('without the capability the Shortcuts card keeps the classic UIKit button', (tester) async {
      await pumpPrivacy(tester, shortcutsAvailable: true, capabilities: const []);
      // The classic Siri switch sits in a coloured container; ListTile reports that in debug builds.
      expect(tester.takeException(), isA<FlutterError>());

      expect(surfaceView(), findsNothing);
      expect(find.byKey(const Key('siri_shortcuts_settings')), findsOneWidget);
      expect(shortcutsButton(), findsOneWidget);
    });

    testWidgets('without App Shortcuts the native list has no Shortcuts card', (tester) async {
      final host = await pumpPrivacy(tester, shortcutsAvailable: false, capabilities: ['shortcuts_link']);

      expect(surfaceView(), findsOneWidget);
      final snapshot = _snapshot(host);
      expect(_sectionIds(snapshot), contains('siri'));
      expect(_sectionIds(snapshot), isNot(contains('siri_shortcuts')));
      expect(_rows(snapshot).values.where((row) => row['kind'] == 'shortcuts_link'), isEmpty);
    });
  });

  group('Assistant voice settings', () {
    Future<NativeTestHost> pumpVoice(WidgetTester tester,
        {List<String>? patched,
        Future<void> Function(String id)? onPreview,
        Future<void> Function()? onStop,
        void Function()? onRevoke}) async {
      final host = NativeTestHost.install();
      await tester.pumpWidget(NativeTestHost.app(VoiceSettingsPage(
          api: _voicesApi(patched: patched),
          onPreview: onPreview ?? (_) async {},
          onStopPreview: onStop ?? () async {},
          onRevokeReadAloud: onRevoke)));
      await tester.pumpAndSettle();
      await NativeTestHost.settle(tester);
      return host;
    }

    testWidgets('projects the current voice, its preview, the mode and read-aloud', (tester) async {
      final host = await pumpVoice(tester);
      final rows = _rows(_snapshot(host));

      expect(rows['voice_current']!['subtitle'], 'Kore');
      expect(rows['voice_current']!['enabled'], true);
      expect(rows['voice_preview_current']!['symbol'], 'play.fill');
      expect(rows['voice_mode']!['value'], '1');
      expect((rows['voice_mode']!['options'] as List).map((option) => option['id']), ['0', '1', '2']);
      expect(rows['voice_read_aloud']!['value'], false);
    });

    testWidgets('mode Off persists and revokes read-aloud; turning read-aloud off revokes too', (tester) async {
      var revoked = 0;
      final host = await pumpVoice(tester, onRevoke: () => revoked++);

      expect(await _send(host, 'voice_read_aloud', true), isNull);
      await tester.pump();
      expect(SharedPreferencesUtil().readChatRepliesAloud, isTrue);
      expect(revoked, 0);

      expect(await _send(host, 'voice_mode', '0'), isNull);
      await tester.pump();
      expect(SharedPreferencesUtil().voiceResponseMode, 0);
      expect(revoked, 1);
      expect(await _send(host, 'voice_mode', '7'), 'invalid_native_action', reason: 'only the offered modes');

      expect(await _send(host, 'voice_read_aloud', false), isNull);
      expect(SharedPreferencesUtil().readChatRepliesAloud, isFalse);
      expect(revoked, 2);
    });

    testWidgets('the current preview is disabled while it runs', (tester) async {
      final gate = Completer<void>();
      final previews = <String>[];
      final host = await pumpVoice(tester, onPreview: (id) {
        previews.add(id);
        return gate.future;
      });

      // The command answers once its preview ends.
      final first = _send(host, 'voice_preview_current');
      await NativeTestHost.settle(tester);
      final busy = _rows(_snapshot(host))['voice_preview_current']!;
      expect(busy['enabled'], false);
      expect(busy['symbol'], 'hourglass');
      expect(await _send(host, 'voice_preview_current'), 'invalid_native_action');
      expect(previews, ['Kore']);

      gate.complete();
      expect(await first, isNull);
      await NativeTestHost.settle(tester);
      expect(_rows(_snapshot(host))['voice_preview_current']!['enabled'], true);
    });

    testWidgets('picking from the picker opened by the native row saves once; closing stops the preview',
        (tester) async {
      final patched = <String>[];
      var stops = 0;
      final host = await pumpVoice(tester, patched: patched, onStop: () async => stops++);

      // The command answers once the picker closes.
      final opened = _send(host, 'voice_current');
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('settings_voice_preview_Puck')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('settings_voice_Puck')));
      await tester.pumpAndSettle();

      expect(await opened, isNull);
      expect(patched, ['Puck']);
      expect(stops, 1);
    });

    testWidgets('native picker rows pop the voice at their index and preview without saving', (tester) async {
      final host = NativeTestHost.install();
      final previewing = ValueNotifier<String?>(null);
      addTearDown(previewing.dispose);
      final previews = <String>[];
      const voices = [
        AssistantVoice(id: 'Charon', name: 'Charon'),
        AssistantVoice(id: 'Kore', name: 'Kore'),
        AssistantVoice(id: 'Puck', name: 'Puck'),
      ];
      String? picked;
      await tester.pumpWidget(NativeTestHost.app(Builder(
          builder: (context) => TextButton(
              onPressed: () async {
                picked = await Navigator.of(context).push<String>(MaterialPageRoute(
                    builder: (_) => NativeVoicePicker(
                        voices: voices,
                        selectedId: 'Kore',
                        previewing: previewing,
                        saving: false,
                        onPreview: (id) async => previews.add(id),
                        fallback: const Text('flutter picker'))));
              },
              child: const Text('open')))));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await NativeTestHost.settle(tester);

      var rows = _rows(_snapshot(host));
      expect(rows['voice:1']!['symbol'], 'checkmark');
      expect(rows['voice:2']!['symbol'], isNull);
      expect(await _send(host, 'voice_preview:2'), isNull);
      expect(previews, ['Puck']);

      previewing.value = 'Puck';
      await NativeTestHost.settle(tester);
      rows = _rows(_snapshot(host));
      expect(rows['voice_preview:0']!['enabled'], false, reason: 'one preview at a time');
      expect(rows['voice_preview:2']!['symbol'], 'hourglass');
      expect(await _send(host, 'voice_preview:0'), 'invalid_native_action');

      expect(await _send(host, 'voice:2'), isNull);
      await tester.pumpAndSettle();
      expect(picked, 'Puck');
    });

    testWidgets('a selection outside the catalog checks no picker row', (tester) async {
      final host = NativeTestHost.install();
      final previewing = ValueNotifier<String?>(null);
      addTearDown(previewing.dispose);
      await tester.pumpWidget(NativeTestHost.app(NativeVoicePicker(
          voices: const [AssistantVoice(id: 'Kore', name: 'Kore')],
          selectedId: 'Retired',
          previewing: previewing,
          saving: false,
          onPreview: (_) async {},
          fallback: const Text('flutter picker'))));
      await NativeTestHost.settle(tester);
      expect(_rows(_snapshot(host)).values.where((row) => row['symbol'] == 'checkmark'), isEmpty);
    });
  });

  group('Wrapped 2025', () {
    Future<NativeTestHost> pumpWrapped(WidgetTester tester, Future<Wrapped2025Response?> Function() fetch,
        {Future<Wrapped2025Response?> Function()? generate}) async {
      final host = NativeTestHost.install();
      await tester.pumpWidget(NativeTestHost.app(Wrapped2025Page(fetchWrapped: fetch, startGeneration: generate)));
      await NativeTestHost.settle(tester);
      return host;
    }

    Future<Wrapped2025Response?> respond(WrappedStatus status,
            {Map<String, dynamic>? result, Map<String, dynamic>? progress, String? error}) async =>
        Wrapped2025Response(status: status, result: result, progress: progress, error: error);

    testWidgets('not generated offers Generate, which starts generation', (tester) async {
      var started = 0;
      final host = await pumpWrapped(tester, () => respond(WrappedStatus.notGenerated), generate: () async {
        started++;
        return Wrapped2025Response(status: WrappedStatus.error);
      });
      final rows = _rows(_snapshot(host));
      expect(rows['wrapped_rewind']!['title'], _l10n.wrappedLetsHitRewind);
      expect(rows['wrapped_generate']!['enabled'], true);

      expect(await _send(host, 'wrapped_generate'), isNull);
      await NativeTestHost.settle(tester);
      expect(started, 1);
      expect(_rows(_snapshot(host)).keys, containsAll(['wrapped_error', 'wrapped_retry']));
    });

    testWidgets('processing progress stays within 0..1 whatever the server reports', (tester) async {
      var pct = 1.7;
      final host = await pumpWrapped(
          tester, () => respond(WrappedStatus.processing, progress: {'step': 'Reading your year', 'pct': pct}));
      var progress = _rows(_snapshot(host))['wrapped_progress']!;
      expect(progress['kind'], 'progress');
      expect(progress['title'], 'Reading your year');
      expect(progress['value'], 1.0);
      expect(progress['maximumValue'], 1.0);
      expect(progress['subtitle'], '100%');

      pct = -0.4;
      await tester.pump(const Duration(seconds: 3));
      await NativeTestHost.settle(tester);
      progress = _rows(_snapshot(host))['wrapped_progress']!;
      expect(progress['value'], 0.0);
      expect(progress['subtitle'], '0%');
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('error offers a retry', (tester) async {
      final host = await pumpWrapped(tester, () => respond(WrappedStatus.error, error: 'Out of credits'));
      final rows = _rows(_snapshot(host));
      expect(rows['wrapped_error']!['subtitle'], 'Out of credits');
      expect(rows['wrapped_retry']!['enabled'], true);
    });

    testWidgets('done projects every card with view tracking and its own share', (tester) async {
      final host = await pumpWrapped(tester, () => respond(WrappedStatus.done, result: _wrappedResult));
      final snapshot = _snapshot(host);
      final sections = (snapshot['sections'] as List).cast<Map>();
      expect(sections, hasLength(13));
      for (final section in sections) {
        expect(((section['rows'] as List).first as Map)['visibilityEnabled'], true, reason: '${section['id']}');
      }
      final rows = _rows(snapshot);
      expect(rows['wrapped_minutes']!['title'], '750');
      expect(rows['wrapped_conversations']!['title'], '1,200');
      expect(rows['wrapped_category:0']!['value'], 0.75);
      expect(rows['wrapped_category:0']!['subtitle'], '75%');
      expect(rows['wrapped_day:0']!['title'], '🎉 Beach day');
      expect(rows['wrapped_buddy:0']!['title'], '🎸 Sam');
      expect(rows['wrapped_movie:0']!['title'], '🎬 The Matrix');
      expect(rows['wrapped_phrase:0']!['title'], 'let us ship it');
      expect(
          rows.keys.where((id) => id.startsWith('wrapped_share:')),
          containsAll([
            for (final card in [
              'stats',
              'categories',
              'actions',
              'days',
              'moments',
              'buddies',
              'obsessions',
              'movies',
              'struggle',
              'win',
              'phrases',
              'collage'
            ])
              'wrapped_share:$card'
          ]));
    });

    testWidgets('a share row captures its Flutter template as a PNG behind the mounted native view', (tester) async {
      final directory = Directory.systemTemp.createTempSync('wrapped_share_test');
      addTearDown(() => directory.deleteSync(recursive: true));
      const pathProvider = MethodChannel('plugins.flutter.io/path_provider');
      const share = MethodChannel('dev.fluttercommunity.plus/share');
      final shared = <Map>[];
      _messenger.setMockMethodCallHandler(pathProvider, (call) async => directory.path);
      _messenger.setMockMethodCallHandler(share, (call) async {
        shared.add(call.arguments as Map);
        return 'dev.fluttercommunity.plus/share/unavailable';
      });
      addTearDown(() {
        _messenger.setMockMethodCallHandler(pathProvider, null);
        _messenger.setMockMethodCallHandler(share, null);
      });
      final host = NativeTestHost.install();
      await tester.pumpWidget(NativeTestHost.app(Scaffold(
          body: Wrapped2025Page(
              fetchWrapped: () async => Wrapped2025Response(status: WrappedStatus.done, result: _wrappedResult)))));
      await NativeTestHost.settle(tester);

      expect(await _send(host, 'wrapped_share:stats'), isNull);
      await tester.pump();
      expect(find.byType(templates.YearInNumbersShareTemplate), findsOneWidget);
      expect(find.byType(UiKitView), findsOneWidget, reason: 'the native view stays mounted');
      for (var step = 0; step < 20 && shared.isEmpty; step++) {
        await tester.pump(const Duration(milliseconds: 100));
        await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 20)));
      }

      expect(shared, hasLength(1));
      final png = File('${directory.path}/omi_wrapped_stats.png').readAsBytesSync();
      expect(png.sublist(1, 4), utf8.encode('PNG'));
      await tester.pump();
      expect(find.byType(templates.YearInNumbersShareTemplate), findsNothing, reason: 'the template is cleared');

      // Every other card shares its own template, under its own file name.
      const files = {
        'categories': 'omi_wrapped_categories',
        'actions': 'omi_wrapped_actions',
        'days': 'omi_wrapped_days',
        'moments': 'omi_wrapped_moments',
        'buddies': 'omi_wrapped_buddies',
        'obsessions': 'omi_wrapped_obsessions',
        'movies': 'omi_wrapped_movies',
        'struggle': 'omi_wrapped_struggle',
        'win': 'omi_wrapped_win',
        'phrases': 'omi_wrapped_phrases',
        'collage': 'omi_wrapped_2025',
      };
      for (final MapEntry(key: card, value: file) in files.entries) {
        final before = shared.length;
        expect(await _send(host, 'wrapped_share:$card'), isNull);
        for (var step = 0; step < 20 && shared.length == before; step++) {
          await tester.pump(const Duration(milliseconds: 100));
          await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 20)));
        }
        expect(shared, hasLength(before + 1), reason: card);
        expect(((shared.last['paths'] as List).single as String).endsWith('/$file.png'), isTrue, reason: card);
        await tester.pump();
      }
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('a malformed result keeps the classic page, which fails on it exactly as without the flag',
        (tester) async {
      await pumpWrapped(
          tester,
          () => respond(WrappedStatus.done, result: {
                ..._wrappedResult,
                'top_categories': [42],
              }));
      expect(find.byType(UiKitView), findsNothing);
      // The classic page reads the same field; it fails exactly as it does without the native flag.
      expect(tester.takeException(), isA<TypeError>());
    });

    testWidgets('polling stops on a session change, even with a poll in flight', (tester) async {
      final host = NativeTestHost.install();
      var fetches = 0;
      Completer<Wrapped2025Response?>? pending;
      await tester.pumpWidget(NativeTestHost.app(Wrapped2025Page(fetchWrapped: () {
        fetches++;
        if (fetches == 1) return respond(WrappedStatus.processing, progress: {'step': 'Starting', 'pct': 0.1});
        return (pending = Completer<Wrapped2025Response?>()).future;
      })));
      await NativeTestHost.settle(tester);
      expect(host.created, isNotEmpty);

      await tester.pump(const Duration(seconds: 3));
      expect(fetches, 2, reason: 'the first poll is in flight');

      final previous = AuthService.installLocalHarnessTokenGateway(const _AnotherOwner());
      addTearDown(() {
        AuthService.installLocalHarnessTokenGateway(previous);
        AuthService.instance.captureSessionSnapshot();
      });
      AuthService.instance.captureSessionSnapshot();
      pending!.complete(Wrapped2025Response(status: WrappedStatus.done, result: _wrappedResult));
      await tester.pump();
      await tester.pump(const Duration(seconds: 10));

      expect(fetches, 2, reason: 'no poll after the session changed');
      // The surface invalidates rather than updates after the session change, so read its dispatch rows.
      final ids =
          IosNativeSurface.debugDispatchRows(tester.state(find.byType(IosNativeSurface))).map((row) => row.id).toList();
      expect(ids, contains('wrapped_progress'), reason: 'the in-flight done result was never applied');
      expect(ids.where((id) => id.startsWith('wrapped_share:') || id.startsWith('wrapped_card:')), isEmpty);
      await tester.pumpWidget(const SizedBox());
    });
  });

  group('Voice profile from Settings', () {
    testWidgets('the native guided voice screen carries the route back row', (tester) async {
      final host = NativeTestHost.install();
      final flow = GuidedVoiceController(FakeVoiceIO());
      addTearDown(flow.dispose);
      await tester.pumpWidget(NativeTestHost.app(VoiceProfileRoute(controller: flow)));
      await NativeTestHost.settle(tester);

      expect(find.byType(UiKitView), findsOneWidget);
      expect(find.byType(AppBar), findsNothing);
      expect(_rows(_snapshot(host))['voice_profile_back']!['symbol'], 'chevron.left');
    });

    testWidgets('without the native renderer the original page chrome stays', (tester) async {
      final flow = GuidedVoiceController(FakeVoiceIO());
      addTearDown(flow.dispose);
      await tester.pumpWidget(NativeTestHost.app(VoiceProfileRoute(controller: flow)));
      await tester.pump();

      expect(find.byType(UiKitView), findsNothing);
      expect(find.byType(AppBar), findsOneWidget);
      expect(find.byType(OmiBackButton), findsOneWidget);
    });
  });

  group('Conversation timeout', () {
    testWidgets('a native option persists exactly that value', (tester) async {
      final host = NativeTestHost.install();
      SharedPreferencesUtil().conversationSilenceDuration = 120;
      await tester.pumpWidget(NativeTestHost.app(Scaffold(
          body: Builder(
              builder: (context) => TextButton(
                  onPressed: () => ConversationTimeoutDialog.show(context,
                      debugPresentNative: (context, nativeBuilder) =>
                          Navigator.of(context).push<int>(MaterialPageRoute(builder: nativeBuilder))),
                  child: const Text('open'))))));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await NativeTestHost.settle(tester);

      final rows = _rows(_snapshot(host));
      expect(rows.keys.where((id) => id.startsWith('timeout:')),
          ['timeout:120', 'timeout:300', 'timeout:600', 'timeout:1800', 'timeout:-1']);
      expect(rows['timeout:120']!['symbol'], 'checkmark');
      expect(rows['timeout:600']!['symbol'], isNull);
      expect(rows['timeout:600']!['subtitle'], _l10n.timeout10MinutesDesc);
      expect(await _send(host, 'timeout:999'), 'invalid_native_action');

      expect(await _send(host, 'timeout:600'), isNull);
      await tester.pumpAndSettle();
      expect(SharedPreferencesUtil().conversationSilenceDuration, 600);
      expect(find.text(_l10n.conversationEndAfterMinutes(10)), findsOneWidget);
    });
  });

  group('JSON editor', () {
    Future<NativeTestHost> pumpEditor(WidgetTester tester, String json) async {
      final host = NativeTestHost.install();
      await tester.pumpWidget(NativeTestHost.app(TranscriptionJsonEditorPage(
          title: 'Request configuration', initialJson: json, provider: SttProvider.custom, onReset: () => {})));
      await NativeTestHost.settle(tester);
      return host;
    }

    testWidgets('the native field holds 262,144 units and Save stays off while the JSON is invalid', (tester) async {
      final host = await pumpEditor(tester, '{}');
      expect(_rows(_snapshot(host))['json_text']!['maximumLength'], 262144);
      expect(_rows(_snapshot(host))['json_save']!['enabled'], true);

      expect(await _send(host, 'json_text', '{'), isNull);
      await NativeTestHost.settle(tester);
      expect(_rows(_snapshot(host))['json_save']!['enabled'], false);
      expect(await _send(host, 'json_save'), 'invalid_native_action');
      expect(_rows(_snapshot(host)).keys, contains('json_error'));
    });

    testWidgets('a configuration above the cap keeps the complete Flutter editor for good', (tester) async {
      await pumpEditor(tester, jsonEncode({'fixture': 'x' * 262144}));
      expect(find.byType(UiKitView), findsNothing);
      expect(find.byType(TextField), findsOneWidget);

      await tester.enterText(find.byType(TextField), '{}');
      await NativeTestHost.settle(tester);
      expect(find.byType(UiKitView), findsNothing, reason: 'shortening the text never swaps editors mid-edit');
    });
  });

  group('Import configuration', () {
    late List<String?> clipboard;

    setUp(() {
      clipboard = [];
    });

    Future<Future<String?>> openImport(WidgetTester tester) async {
      NativeTestHost.install();
      _messenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
        if (call.method == 'Clipboard.getData') {
          final text = clipboard.removeAt(0);
          return text == null ? null : {'text': text};
        }
        return null;
      });
      addTearDown(() => _messenger.setMockMethodCallHandler(SystemChannels.platform, null));
      late BuildContext context;
      await tester.pumpWidget(NativeTestHost.app(Builder(builder: (built) {
        context = built;
        return const SizedBox();
      })));
      final result = showImportConfigDialog(context);
      await tester.pump();
      return result;
    }

    Map<String, Object?> reply(String action, String text) => {
          'action': action,
          'values': {'import_json': text},
        };

    String jsonValue(Map snapshot) => _rows(snapshot)['import_json']!['value'] as String;

    testWidgets('Paste re-presents the sheet with the clipboard text, then Import returns it', (tester) async {
      clipboard = ['{"provider":"custom"}'];
      final presented = _answerConfig(
          present: (snapshot) =>
              jsonValue(snapshot).isEmpty ? reply('paste', '') : reply('import', jsonValue(snapshot)));
      final result = await openImport(tester);
      await tester.pumpAndSettle();

      expect(await result, '{"provider":"custom"}');
      expect(presented, hasLength(2));
      final rows = _rows(presented.first);
      expect(rows['import_json']!['maximumLength'], 262144);
      expect(rows['import_hint']!['title'], _l10n.pasteJsonConfig);
      expect(rows['import_api_key']!['title'], _l10n.addApiKeyAfterImport);
      expect(rows.keys, containsAll(['cancel', 'paste', 'import']));
      expect(jsonValue(presented.last), '{"provider":"custom"}');
    });

    testWidgets('an over-cap clipboard is returned directly for import, uncut', (tester) async {
      final large = 'x' * 262145;
      clipboard = [large];
      final presented = _answerConfig(present: (_) => reply('paste', ''));
      final result = await openImport(tester);
      await tester.pumpAndSettle();

      expect(await result, large);
      expect(presented, hasLength(1), reason: 'the native field never receives more than it holds');
    });

    testWidgets('Cancel imports nothing and never reads the clipboard', (tester) async {
      clipboard = ['{"unused":true}'];
      _answerConfig(present: (_) => {'action': 'cancel', 'values': <String, Object?>{}});
      final result = await openImport(tester);
      await tester.pumpAndSettle();

      expect(await result, isNull);
      expect(clipboard, hasLength(1));
    });

    testWidgets('a refused presentation opens the Flutter dialog', (tester) async {
      _answerConfig(present: (_) => PlatformException(code: 'invalid_native_presentation'));
      final result = await openImport(tester);
      await tester.pumpAndSettle();

      expect(find.byType(OmiAlertDialog), findsOneWidget);
      await tester.enterText(find.byType(TextField), '{"a":1}');
      await tester.tap(find.text(_l10n.import));
      await tester.pumpAndSettle();
      expect(await result, '{"a":1}');
    });
  });
}

const _wrappedResult = <String, dynamic>{
  'total_time_hours': 12.5,
  'total_conversations': 1200,
  'days_active': 210,
  'category_breakdown': [
    {'category': 'work', 'count': 75},
    {'category': 'personal_life', 'count': 25},
  ],
  'top_categories': ['work', 'personal_life'],
  'total_action_items': 40,
  'completed_action_items': 30,
  'action_items_completion_rate': 0.75,
  'memorable_days': {
    'most_fun_day': {'emoji': '🎉', 'title': 'Beach day', 'description': 'Sun', 'date': 'July 4'},
  },
  'funniest_event': {'title': 'The cake', 'story': 'It fell', 'date': 'May 2'},
  'most_embarrassing_event': {'title': 'Wrong room', 'story': 'Oops', 'date': 'March 9'},
  'top_buddies': [
    {'name': 'Sam', 'relationship': 'Bandmate', 'context': 'Rehearsals', 'emoji': '🎸'},
  ],
  'obsessions': {'show': 'severance', 'movie': 'dune', 'book': 'piranesi', 'celebrity': 'nobody', 'food': 'ramen'},
  'movie_recommendations': ['the matrix'],
  'struggle': {'title': 'Sleep'},
  'personal_win': {'title': 'Ran a marathon'},
  'top_phrases': [
    {'phrase': 'let us ship it'},
    'sounds good',
  ],
};

http.Response _json(int status, Object body) => http.Response(jsonEncode(body), status);

AssistantVoicesApi _voicesApi({List<String>? patched}) => AssistantVoicesApi(send: (request) async {
      if (request.method == 'PATCH') {
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        patched?.add(body['voice_id'] as String);
        return _json(200, {'voice_id': body['voice_id']});
      }
      if (request.url.endsWith('v1/tts/voices')) {
        return _json(200, {
          'voices': [
            {'id': 'Charon', 'name': 'Charon'},
            {'id': 'Kore', 'name': 'Kore'},
            {'id': 'Puck', 'name': 'Puck'},
          ],
          'default_voice_id': 'Charon',
        });
      }
      if (request.url.endsWith('v1/users/voice')) return _json(200, {'voice_id': 'Kore'});
      return _json(404, {});
    });

class _SiriHost extends SiriIndexApi {
  _SiriHost(this.available);
  final bool available;

  @override
  Future<bool> appShortcutsAvailable() async => available;

  @override
  Future<bool> isEnabled() async => true;
}

final class _AnotherOwner implements AuthTokenGateway {
  const _AnotherOwner();

  @override
  AuthUserSnapshot? get currentUser => const AuthUserSnapshot(uid: 'another-owner');

  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;

  @override
  Future<void> signOut() async {}
}
