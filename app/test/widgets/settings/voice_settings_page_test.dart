import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/assistant_voices.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/voice_settings_page.dart';
import 'package:omi/ui/ui.dart';

http.Response _json(int status, Object body) => http.Response(jsonEncode(body), status);

const _catalog = {
  'voices': [
    {'id': 'Charon', 'name': 'Charon'},
    {'id': 'Kore', 'name': 'Kore'},
    {'id': 'Puck', 'name': 'Puck'},
  ],
  'default_voice_id': 'Charon',
};

AssistantVoicesApi _api({String selected = 'Kore', Map<String, int> patchStatus = const {}, List<String>? patched}) {
  return AssistantVoicesApi(
    send: (request) async {
      if (request.method == 'PATCH') {
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        patched?.add(body['voice_id'] as String);
        final status = patchStatus[body['voice_id']] ?? 200;
        return _json(status, status == 200 ? {'voice_id': body['voice_id']} : {'error': 'no'});
      }
      if (request.url.endsWith('v1/tts/voices')) return _json(200, _catalog);
      if (request.url.endsWith('v1/users/voice')) return _json(200, {'voice_id': selected});
      return _json(404, {});
    },
  );
}

Future<void> _pump(
  WidgetTester tester, {
  AssistantVoicesApi? api,
  Future<void> Function(String voiceId)? onPreview,
  Future<void> Function()? onStopPreview,
}) async {
  tester.view.physicalSize = const Size(1200, 4000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      locale: const Locale('en'),
      home: VoiceSettingsPage(api: api ?? _api(), onPreview: onPreview, onStopPreview: onStopPreview),
    ),
  );
  await tester.pumpAndSettle();
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
  final en = lookupAppLocalizations(const Locale('en'));

  setUpAll(() {
    try {
      Env.init(_TestEnvFields());
    } catch (_) {}
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'uid-a'});
    await SharedPreferencesUtil.init();
  });

  testWidgets('loads and renders mode row, off-by-default toggle, and the persisted voice', (tester) async {
    await _pump(tester);

    expect(find.byKey(const ValueKey('settings_page_voice')), findsOneWidget);
    expect(find.text(en.voiceResponseMode), findsOneWidget);
    expect(find.text(en.readChatRepliesAloud), findsOneWidget);
    expect(find.text(en.readChatRepliesAloudDescription), findsOneWidget);
    expect(SharedPreferencesUtil().readChatRepliesAloud, isFalse);
    expect(find.text('Kore'), findsOneWidget);
  });

  testWidgets('read-aloud toggle persists per account without touching voice mode', (tester) async {
    await _pump(tester);
    await tester.tap(find.byKey(const ValueKey('settings_row_readChatRepliesAloud')));
    await tester.pumpAndSettle();
    expect(SharedPreferencesUtil().readChatRepliesAloud, isTrue);
    expect(SharedPreferencesUtil().voiceResponseMode, 1);
  });

  testWidgets('picker preview sends the voice id without saving it', (tester) async {
    final previews = <String>[];
    final patched = <String>[];
    await _pump(
      tester,
      api: _api(patched: patched),
      onPreview: (id) async => previews.add(id),
    );

    await tester.tap(find.byKey(const ValueKey('settings_row_assistantVoice')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('settings_voice_preview_Puck')));
    await tester.pumpAndSettle();

    expect(previews, ['Puck']);
    expect(patched, isEmpty);
  });

  testWidgets('selecting a voice PATCHes and shows the acked value', (tester) async {
    final patched = <String>[];
    await _pump(tester, api: _api(patched: patched));

    await tester.tap(find.byKey(const ValueKey('settings_row_assistantVoice')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('settings_voice_Puck')));
    await tester.pumpAndSettle();

    expect(patched, ['Puck']);
    expect(find.text('Puck'), findsOneWidget);
  });

  testWidgets('a failed PATCH keeps the previous selection', (tester) async {
    final patched = <String>[];
    await _pump(
      tester,
      api: _api(patched: patched, patchStatus: const {'Puck': 503}),
    );

    await tester.tap(find.byKey(const ValueKey('settings_row_assistantVoice')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('settings_voice_Puck')));
    await tester.pumpAndSettle();

    expect(patched, ['Puck']);
    expect(find.text('Kore'), findsWidgets);
  });

  testWidgets('leaving the page stops an in-flight preview', (tester) async {
    var stops = 0;
    await _pump(tester, onStopPreview: () async => stops++);
    expect(stops, 0);
    await tester.pumpWidget(const MaterialApp(home: SizedBox()));
    await tester.pumpAndSettle();
    expect(stops, 1);
  });

  testWidgets('closing the picker sheet stops an in-flight preview without an error toast', (tester) async {
    var stops = 0;
    var previews = 0;
    await _pump(tester, onPreview: (id) async => previews++, onStopPreview: () async => stops++);

    await tester.tap(find.byKey(const ValueKey('settings_row_assistantVoice')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('settings_voice_preview_Puck')));
    await tester.pumpAndSettle();
    expect(previews, 1);

    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(stops, 1);
    expect(find.text(en.somethingWentWrong), findsNothing);
  });

  testWidgets('a failed PATCH clears the saving state so a retry can run', (tester) async {
    final patched = <String>[];
    await _pump(
      tester,
      api: _api(patched: patched, patchStatus: const {'Puck': 503}),
    );

    await tester.tap(find.byKey(const ValueKey('settings_row_assistantVoice')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('settings_voice_Puck')));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('settings_row_assistantVoice')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('settings_voice_Charon')));
    await tester.pumpAndSettle();

    expect(patched, ['Puck', 'Charon']);
    expect(find.text('Charon'), findsWidgets);
  });

  testWidgets('an owner change mid-session never PATCHes the new account from stale UI', (tester) async {
    final patched = <String>[];
    await _pump(tester, api: _api(patched: patched));

    SharedPreferencesUtil().uid = 'uid-b';

    await tester.tap(find.byKey(const ValueKey('settings_row_assistantVoice')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('settings_voice_Puck')));
    await tester.pumpAndSettle();

    expect(patched, isEmpty);
  });

  testWidgets('an in-flight preview shows a spinner in the sheet and disables other previews', (tester) async {
    final gate = Completer<void>();
    var stops = 0;
    await _pump(tester, onPreview: (id) => gate.future, onStopPreview: () async => stops++);

    await tester.tap(find.byKey(const ValueKey('settings_row_assistantVoice')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('settings_voice_preview_Puck')));
    await tester.pump();

    expect(find.byType(OmiSpinner), findsWidgets);
    final busyButton = tester.widget<OmiIconButton>(find.byKey(const ValueKey('settings_voice_preview_Puck')));
    expect(busyButton.onPressed, isNull);
    final otherButton = tester.widget<OmiIconButton>(find.byKey(const ValueKey('settings_voice_preview_Kore')));
    expect(otherButton.onPressed, isNull);

    gate.complete();
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(stops, 1);
    expect(find.text(en.somethingWentWrong), findsNothing);
  });

  testWidgets('load failure shows the error state with retry', (tester) async {
    await _pump(tester, api: AssistantVoicesApi(send: (_) async => _json(503, {'error': 'down'})));
    expect(find.byType(OmiErrorState), findsOneWidget);
    expect(find.text(en.tryAgain), findsOneWidget);
  });
}
