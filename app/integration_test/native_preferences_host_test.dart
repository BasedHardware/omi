import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/api/assistant_voices.dart';
import 'package:omi/backend/http/api/wrapped.dart';
import 'package:omi/pages/settings/transcription/transcription_dialogs.dart';
import 'package:omi/pages/settings/voice_settings_page.dart';
import 'package:omi/pages/settings/wrapped_2025_page.dart';
import 'package:omi/pages/settings/wrapped_2025_share_templates.dart' as templates;

import 'journeys/support/hermetic_boot.dart';
import 'support/native_host_harness.dart';

/// Simulator host checks for the preferences, Shortcuts and Wrapped batch. Run with
/// OMI_APP_PROFILE=local_dev and OMI_IOS_SWIFTUI=true. On a Siri-toolchain build, also confirm by hand
/// that the Data & Privacy ShortcutsLink opens the Shortcuts app.
void main() {
  runNativeHostSuite((checkNativeHost) {
    testWidgets('Wrapped share capture still produces a PNG with the platform view mounted', (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      await tester.pumpWidget(nativeHostApp(Wrapped2025Page(
          fetchWrapped: () async => Wrapped2025Response(status: WrappedStatus.done, result: _wrappedResult))));
      await checkNativeHost(tester, 'native-preferences-shortcuts-wrapped-wrapped-dark');

      // The share sheet itself is replaced so the run stays unattended; capture and file are real.
      final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      const share = MethodChannel('dev.fluttercommunity.plus/share');
      final shared = <Map>[];
      messenger.setMockMethodCallHandler(share, (call) async {
        shared.add(call.arguments as Map);
        return 'dev.fluttercommunity.plus/share/unavailable';
      });
      addTearDown(() => messenger.setMockMethodCallHandler(share, null));

      await nativeProjectedRow(tester, 'wrapped_share:stats').action!(null);
      await tester.pump();
      expect(find.byType(templates.YearInNumbersShareTemplate), findsOneWidget);
      expect(find.byType(UiKitView), findsOneWidget, reason: 'the native view stays mounted while sharing');
      final deadline = DateTime.now().add(const Duration(seconds: 10));
      while (shared.isEmpty && DateTime.now().isBefore(deadline)) {
        await Future<void>.delayed(const Duration(milliseconds: 100));
        await tester.pump();
      }

      expect(shared, hasLength(1));
      final path = (shared.single['paths'] as List).single as String;
      final png = File(path).readAsBytesSync();
      expect(png.length, greaterThan(1000));
      expect(png.sublist(1, 4), utf8.encode('PNG'));
      expect(find.byType(UiKitView), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
      await tester.pump();
      expect(tester.takeException(), isNull);
    });

    testWidgets('voice settings open the native picker over the existing voice owner', (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      final patched = <String>[];
      var stops = 0;
      await tester.pumpWidget(nativeHostApp(VoiceSettingsPage(
          api: _voicesApi(patched),
          onPreview: (_) async {},
          onStopPreview: () async => stops++,
          onRevokeReadAloud: () {})));
      await checkNativeHost(tester, 'native-preferences-shortcuts-wrapped-voice-dark');
      expect(nativeProjectedRow(tester, 'voice_current').subtitle, 'Kore');

      await nativeProjectedRow(tester, 'voice_current').action!(null);
      await tester.pump(const Duration(seconds: 1));
      await tester.pump(const Duration(seconds: 1));
      expect(find.byType(NativeVoicePicker), findsOneWidget);
      expect(nativeProjectedRow(tester, 'voice:1').symbol, 'checkmark');
      await nativeProjectedRow(tester, 'voice:2').action!(null);
      await tester.pump(const Duration(seconds: 1));
      await tester.pump(const Duration(seconds: 1));

      expect(patched, ['Puck']);
      expect(stops, 1, reason: 'closing the picker stops any preview');
      expect(nativeProjectedRow(tester, 'voice_current').subtitle, 'Puck');
      await tester.pumpWidget(const SizedBox());
      await tester.pump();
      expect(tester.takeException(), isNull);
    });

    testWidgets('import modal Dart paste loop (smoke): a fake clipboard re-presents the pasted text', (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      const json = '{"provider":"custom"}';
      final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
        if (call.method == 'Clipboard.getData') return {'text': json};
        return null;
      });
      addTearDown(() => messenger.setMockMethodCallHandler(SystemChannels.platform, null));
      const config = MethodChannel('com.omi.native_ui/config');
      final presented = <Map>[];
      messenger.setMockMethodCallHandler(config, (call) async {
        if (call.method == 'isSupported') return true;
        if (call.method != 'present') return null;
        final snapshot = (call.arguments as Map)['snapshot'] as Map;
        presented.add(snapshot);
        final row = (snapshot['sections'] as List).cast<Map>().first['rows'] as List;
        final text = (row.cast<Map>().firstWhere((row) => row['id'] == 'import_json'))['value'] as String;
        return {
          'action': text.isEmpty ? 'paste' : 'import',
          'values': {'import_json': text},
        };
      });
      addTearDown(() => messenger.setMockMethodCallHandler(config, null));

      late Future<String?> result;
      await tester.pumpWidget(nativeHostApp(Scaffold(
          body: Builder(
              builder: (context) => TextButton(
                  onPressed: () => result = showImportConfigDialog(context), child: const Text('import'))))));
      await tester.tap(find.text('import'));
      for (var frame = 0; frame < 10; frame++) {
        await tester.pump(const Duration(milliseconds: 100));
      }

      expect(await result, json);
      expect(presented, hasLength(2));
      final rows = (presented.last['sections'] as List).cast<Map>().first['rows'] as List;
      expect(rows.cast<Map>().firstWhere((row) => row['id'] == 'import_json')['value'], json);
      expect(tester.takeException(), isNull);
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
  'top_buddies': [
    {'name': 'Sam', 'relationship': 'Bandmate', 'context': 'Rehearsals', 'emoji': '🎸'},
  ],
  'obsessions': {'show': 'severance', 'movie': 'dune', 'book': 'piranesi', 'celebrity': 'nobody', 'food': 'ramen'},
  'movie_recommendations': ['the matrix'],
  'struggle': {'title': 'Sleep'},
  'personal_win': {'title': 'Ran a marathon'},
  'top_phrases': ['let us ship it'],
};

AssistantVoicesApi _voicesApi(List<String> patched) => AssistantVoicesApi(send: (request) async {
      http.Response json(Object body) => http.Response(jsonEncode(body), 200);
      if (request.method == 'PATCH') {
        final voice = (jsonDecode(request.body) as Map<String, dynamic>)['voice_id'] as String;
        patched.add(voice);
        return json({'voice_id': voice});
      }
      if (request.url.endsWith('v1/tts/voices')) {
        return json({
          'voices': [
            {'id': 'Charon', 'name': 'Charon'},
            {'id': 'Kore', 'name': 'Kore'},
            {'id': 'Puck', 'name': 'Puck'},
          ],
          'default_voice_id': 'Charon',
        });
      }
      return json({'voice_id': 'Kore'});
    });
