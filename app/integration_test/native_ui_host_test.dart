import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';
import 'package:omi/widgets/media_viewer_page.dart';
import 'package:omi/pages/conversation_detail/widgets/name_speaker_sheet.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_home.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/settings/settings_drawer.dart';
import 'package:omi/pages/apps/add_mcp_server_page.dart';
import 'package:omi/pages/apps/markdown_viewer.dart';
import 'package:omi/pages/settings/people.dart';
import 'package:omi/pages/conversations/widgets/create_folder_sheet.dart';
import 'package:omi/pages/memories/widgets/memory_management_sheet.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';
import 'package:omi/pages/onboarding/guided_voice_controller.dart';
import 'package:omi/pages/onboarding/speech_profile_widget.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_step_layout.dart';
import 'package:omi/pages/phone_calls/phone_setup_number_page.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/ui/ui.dart';

import 'journeys/support/hermetic_boot.dart';
import 'visual_audit/fakes.dart';
import 'visual_audit/screen_frame_fixtures.dart';
import '../test/providers/guided_voice_controller_test.dart' show FakeVoiceIO;
import '../test/mobile/native_ui/native_calls_test.dart' show FakeNativeCallOwner;
import 'package:omi/pages/phone_calls/active_call_page.dart';
import 'package:omi/pages/phone_calls/phone_calls_page.dart';

import 'package:omi/pages/apps/update_app.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/action_items/day_tasks_page.dart';
import 'package:omi/pages/settings/fair_use_page.dart';
import 'package:omi/pages/conversations/local_storage_page.dart';
import 'package:omi/pages/conversations/private_cloud_sync_page.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/developer.dart';
import 'package:omi/providers/developer_mode_provider.dart';
import 'package:omi/pages/settings/data_export.dart';
import 'package:omi/pages/apps/widgets/filter_sheet.dart';
import 'package:omi/providers/app_provider.dart';
part 'native_advanced_host_cases.dart';

class _NativePhoneOwner extends PhoneCallProvider {
  _NativePhoneOwner() : super.forTesting();
  final verified = <String>[];
  @override
  Future<bool> startVerification(String phoneNumber) async {
    verified.add(phoneNumber);
    return false;
  }
}

int? nativeViewId(WidgetTester tester, Finder finder) {
  RenderUiKitView? view;
  void visit(RenderObject object) {
    if (object is RenderUiKitView) view = object;
    object.visitChildren(visit);
  }

  visit(tester.renderObject(finder));
  return view?.viewController.id;
}

/// Exercises the actual Flutter platform view, UIKit containment and SwiftUI renderer.
/// Run on Simulator with OMI_APP_PROFILE=local_dev and OMI_IOS_SWIFTUI=true.
void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  Future<List<int>> captureScreenshot(String name) async {
    const port = int.fromEnvironment('NATIVE_UI_SCREENSHOT_PORT');
    if (port != 0) {
      final client = HttpClient()..connectionTimeout = const Duration(seconds: 15);
      try {
        final request = await client.getUrl(Uri.http('127.0.0.1:$port', '/capture', {'name': name}));
        final response = await request.close().timeout(const Duration(seconds: 20));
        expect(response.statusCode, 200, reason: 'The Simulator display capture must finish on this screen');
        await response.drain<void>();
      } finally {
        client.close(force: true);
      }
    }
    return binding.takeScreenshot(name);
  }

  Future<void> checkNativeHost(WidgetTester tester, String screenshot) async {
    await tester.pump(const Duration(seconds: 2));
    await tester.pump(const Duration(seconds: 2));
    final native = find.byType(UiKitView);
    expect(native, findsOneWidget);
    expect(tester.getRect(native).height, greaterThan(550));
    // Platform-view creation is asynchronous on the first native route. Pumping
    // virtual frames alone does not wait for UIKit's real creation reply.
    int? id;
    final deadline = DateTime.now().add(const Duration(seconds: 10));
    while (id == null && DateTime.now().isBefore(deadline)) {
      await Future<void>.delayed(const Duration(milliseconds: 100));
      await tester.pump();
      id = nativeViewId(tester, native);
    }
    expect(id, isNotNull, reason: 'The real UIKit view must finish creating');
    await MethodChannel('com.omi.native_ui/surface/$id')
        .invokeMethod<void>('update', tester.widget<UiKitView>(native).creationParams);
    await Future<void>.delayed(const Duration(seconds: 2));
    await tester.pump();
    final received =
        await MethodChannel('com.omi.native_ui/surface/$id').invokeMapMethod<String, Object?>('debugPresentation');
    final projected = tester.widget<UiKitView>(native).creationParams as Map;
    expect(
        (received!['toolbar'] as List).map((row) => row['id']), (projected['toolbar'] as List).map((row) => row['id']),
        reason: 'The UIKit owner must receive the current navigation projection');
    expect(tester.takeException(), isNull);
    expect(await captureScreenshot(screenshot), isNotEmpty);
  }

  if (!const bool.fromEnvironment('NATIVE_UI_ADVANCED_ONLY')) {
    testWidgets('native conversation detail retains its player across summary, transcript and search', (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      final conversation = ServerConversation(
          id: 'native-reader-fixture',
          createdAt: DateTime(2026, 10, 4, 10),
          status: ConversationStatus.completed,
          structured: Structured('Native conversation',
              '## Next steps\n- **Ship** the reader\n- Check playback\n\n> Preserve the session.'),
          transcriptSegments: [
            TranscriptSegment(
                id: 'first',
                text: 'Ship **literal** transcript text.',
                speaker: 'SPEAKER_0',
                personId: null,
                isUser: true,
                start: 0,
                end: 20,
                translations: []),
            TranscriptSegment(
                id: 'second',
                text: 'Check playback and preserve the session.',
                speaker: 'SPEAKER_1',
                personId: null,
                isUser: false,
                start: 20,
                end: 40,
                translations: []),
          ]);
      final owner = ConversationDetailProvider(fetchConversation: (_) async => conversation);
      addTearDown(owner.dispose);
      await tester.pumpWidget(MultiProvider(
          providers: [
            ...defaultAuditProviders(),
            ChangeNotifierProvider<ConversationDetailProvider>.value(value: owner)
          ],
          child: MaterialApp(
              localizationsDelegates: AppLocalizations.localizationsDelegates,
              supportedLocales: const [Locale('en')],
              theme: buildOmiTheme(brightness: Brightness.dark),
              home: ConversationDetailPage(conversation: conversation, initialTab: ConversationTab.summary))));
      await checkNativeHost(tester, 'real-native-conversation-summary-dark');
      IosNativeSurface surface() => tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
      NativeRow row(String id) => [
            ...surface().toolbar,
            ...surface().sections.expand((s) => s.rows),
            ...?surface().reader?.actions
          ].singleWhere((row) => row.id == id);
      expect(row('detail_summary_content').kind, 'rich_text');
      expect(row('detail_summary_content').blocks.any((block) => block['kind'] == 'heading'), true);
      final player = tester.state(find.byType(ConversationBottomBar, skipOffstage: false));
      final viewId = nativeViewId(tester, find.byType(UiKitView));
      await row('detail_tab').action!('transcript');
      await tester.pump(const Duration(seconds: 1));
      await checkNativeHost(tester, 'real-native-conversation-transcript-dark');
      expect(row('detail_segment:first').title, 'Ship **literal** transcript text.');
      expect(identical(tester.state(find.byType(ConversationBottomBar, skipOffstage: false)), player), true);
      expect(nativeViewId(tester, find.byType(UiKitView)), viewId);
      await surface().search!('playback');
      await tester.pump(const Duration(seconds: 1));
      expect(surface().reader!.targetId, 'detail_segment:second');
      expect(row('detail_search_count').title, '1 / 1');
      await checkNativeHost(tester, 'real-native-conversation-search-dark');
      await row('detail_search_close').action!(null);
      await row('detail_tab').action!('summary');
      await tester.pump(const Duration(seconds: 1));
      expect(identical(tester.state(find.byType(ConversationBottomBar, skipOffstage: false)), player), true);
      await tester.pumpWidget(const SizedBox());
      await tester.pump();
      expect(tester.takeException(), isNull);
    });

    testWidgets('native speaker sheet selects lines and people without saving before Save', (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      final people = PeopleProvider(loadPeople: () async => const PeopleListResponse(people: []))
        ..people = [Person(id: 'friend', name: 'Maya', createdAt: DateTime(2026), updatedAt: DateTime(2026))];
      addTearDown(people.dispose);
      final saves = <List<Object>>[];
      final segments = [
        for (final index in [0, 1])
          TranscriptSegment(
              id: 'line:$index',
              text: 'Line $index',
              speaker: 'SPEAKER_0',
              isUser: true,
              personId: null,
              start: index * 10.0,
              end: index * 10.0 + 10,
              translations: [])
      ];
      await tester.pumpWidget(MultiProvider(
          providers: [...defaultAuditProviders(), ChangeNotifierProvider<PeopleProvider>.value(value: people)],
          child: MaterialApp(
              localizationsDelegates: AppLocalizations.localizationsDelegates,
              supportedLocales: const [Locale('en')],
              theme: buildOmiTheme(brightness: Brightness.dark),
              home: Scaffold(
                  body: NameSpeakerBottomSheet(
                      speakerId: 0,
                      segmentId: 'line:0',
                      segments: segments,
                      onSpeakerAssigned: (speaker, person, name, lines, all) async {
                        saves.add([speaker, person, name, lines, all]);
                        return true;
                      })))));
      await checkNativeHost(tester, 'real-native-speaker-picker-dark');
      NativeRow row(String id) {
        final surface = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
        return [...surface.toolbar, ...surface.sections.expand((s) => s.rows)].singleWhere((row) => row.id == id);
      }

      await row('speaker_add_person').action!(null);
      await tester.pump();
      await row('speaker_new_name').action!('Maya');
      await tester.pump();
      expect(row('speaker_save').enabled, false);
      expect(saves, isEmpty);
      await row('speaker_new_cancel').action!(null);
      await tester.pump();
      await row('speaker_person').action!('friend');
      await row('speaker_apply').action!(true);
      await tester.pump();
      expect(row('speaker_line:line:1').value, true);
      await row('speaker_line:line:1').action!(false);
      await tester.pump();
      expect(row('speaker_apply').value, false);
      expect(saves, isEmpty);
      await row('speaker_save').action!(null);
      expect(saves, [
        [
          0,
          'friend',
          'Maya',
          ['line:0'],
          false
        ]
      ]);
      await tester.pumpWidget(const SizedBox());
      await tester.pump();
      expect(tester.takeException(), isNull);
    });

    testWidgets('native photo viewer loads lazily, pages and removes its temporary images', (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      final frames = await renderScreenFrameFixtures();
      var loads = 0;
      final items = [
        MediaViewerItem(
            bytesLoader: () async {
              loads++;
              return frames.values.first;
            },
            showCaptionStrip: true,
            caption: 'A synthetic meeting screenshot'),
        MediaViewerItem(base64: base64Encode(frames.values.last)),
      ];
      await tester.pumpWidget(MultiProvider(
          providers: defaultAuditProviders(),
          child: MaterialApp(
              localizationsDelegates: AppLocalizations.localizationsDelegates,
              supportedLocales: const [Locale('en')],
              theme: buildOmiTheme(brightness: Brightness.dark),
              home: MediaViewerPage(items: items))));
      await checkNativeHost(tester, 'real-native-media-viewer-dark');
      IosNativeSurface surface() => tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
      final image = surface().sections.single.rows.singleWhere((row) => row.kind == 'image');
      expect(loads, 1);
      final file = File.fromUri(Uri.parse(image.imageUri!));
      expect(await file.exists(), true);
      expect(image.maximumValue, 4);
      await surface().reader!.footer.singleWhere((row) => row.id == 'media_next').action!(null);
      await tester.pump();
      await checkNativeHost(tester, 'real-native-media-second-page-dark');
      expect(surface().title, 'Photos 2 / 2');
      expect(loads, 1);
      await surface().reader!.footer.singleWhere((row) => row.id == 'media_previous').action!(null);
      await tester.pump();
      expect(loads, 1, reason: 'Returning to a page retains its existing image loader');
      await tester.pumpWidget(const SizedBox());
      await tester.pump();
      await Future<void>.delayed(const Duration(milliseconds: 500));
      expect(await file.exists(), false);
      expect(tester.takeException(), isNull);
    });

    testWidgets('native MCP form validates before sending and preserves original connect owner', (tester) async {
      final backend = await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      await tester.pumpWidget(MultiProvider(
          providers: defaultAuditProviders(),
          child: MaterialApp(
              localizationsDelegates: AppLocalizations.localizationsDelegates,
              supportedLocales: const [Locale('en')],
              theme: buildOmiTheme(brightness: Brightness.dark),
              home: const AddMcpServerPage())));
      await checkNativeHost(tester, 'real-native-mcp-setup-dark');
      NativeRow row(String id) {
        final surface = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
        return [...surface.toolbar, ...surface.sections.expand((s) => s.rows)].singleWhere((row) => row.id == id);
      }

      await row('mcp_connect').action!(null);
      await tester.pump();
      expect(backend.countOf('POST', '/v1/apps/mcp'), 0);
      expect(row('mcp_validation_error').title, isNotEmpty);
      await row('mcp_name').action!('Fixture server');
      await row('mcp_url').action!('invalid');
      await tester.pump();
      await row('mcp_connect').action!(null);
      await tester.pump();
      expect(backend.countOf('POST', '/v1/apps/mcp'), 0);
      await row('mcp_url').action!('https://example.com/mcp');
      await tester.pump();
      backend.failNext('POST', '/v1/apps/mcp', status: 400, body: '{"detail":"Synthetic connection refusal"}');
      await row('mcp_connect').action!(null);
      await tester.pump();
      expect(backend.countOf('POST', '/v1/apps/mcp'), 1);
      expect(row('mcp_connect').enabled, true);
      await tester.pumpWidget(const SizedBox());
      await tester.pump();
      expect(tester.takeException(), isNull);
    });

    testWidgets('native setup Markdown keeps links with their Dart owner and uses full reader', (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      await tester.pumpWidget(MultiProvider(
          providers: defaultAuditProviders(),
          child: MaterialApp(
              localizationsDelegates: AppLocalizations.localizationsDelegates,
              supportedLocales: const [Locale('en')],
              theme: buildOmiTheme(brightness: Brightness.dark),
              home: const MarkdownViewer(
                  title: 'Fixture setup',
                  markdown:
                      '## Connect your app\n\n1. **Open** [setup](https://example.com/setup).\n2. Keep your account.\n\n> Use the existing service owner.\n\n    {"mode":"native"}'))));
      await checkNativeHost(tester, 'real-native-markdown-setup-dark');
      final surface = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
      final rows = surface.sections.single.rows;
      expect(surface.reader, isNotNull);
      expect(rows.any((row) => row.blocks.single['kind'] == 'code'), true);
      expect(rows.first.options, {'https://example.com/setup': 'https://example.com/setup'});
      expect(rows.first.projection.toString(), isNot(contains('uid=')));
      await tester.pumpWidget(const SizedBox());
      await tester.pump();
      expect(tester.takeException(), isNull);
    });
  }
  registerNativeAdvancedHostChecks(checkNativeHost);
  if (const bool.fromEnvironment('NATIVE_UI_DETAILS_ONLY') || const bool.fromEnvironment('NATIVE_UI_ADVANCED_ONLY')) {
    return;
  }

  testWidgets('native calls host keeps dialer and active-call commands with their original owner', (tester) async {
    await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
    addTearDown(JourneyHermeticBoot.stop);
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    const contacts = MethodChannel('flutter_contacts');
    const events = 'com.omi/phone_calls/events';
    messenger.setMockMessageHandler(events, (_) async => const StandardMethodCodec().encodeSuccessEnvelope(null));
    messenger.setMockMethodCallHandler(contacts, (call) async => call.method == 'permissions.request' ? 'denied' : []);
    addTearDown(() {
      messenger.setMockMessageHandler(events, null);
      messenger.setMockMethodCallHandler(contacts, null);
    });
    final owner = FakeNativeCallOwner();
    addTearDown(owner.dispose);
    Widget host(Widget page) => MultiProvider(
        providers: [...defaultAuditProviders(), ChangeNotifierProvider<PhoneCallProvider>.value(value: owner)],
        child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: const [Locale('en')],
            theme: buildOmiTheme(brightness: Brightness.dark),
            home: page));
    await tester.pumpWidget(host(const PhoneCallsPage()));
    await checkNativeHost(tester, 'real-native-call-contacts-dark');
    NativeRow row(String id) {
      final surface = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
      return [...surface.toolbar, ...surface.sections.expand((s) => s.rows), ...?surface.chat?.actions]
          .singleWhere((row) => row.id == id);
    }

    expect(row('phone_permission_allow').enabled, true);
    await row('phone_tab').action!('1');
    await tester.pump();
    await checkNativeHost(tester, 'real-native-call-keypad-dark');
    for (final key in ['+', '3', '7', '2']) {
      await row('phone_keypad').action!(key);
      await tester.pump();
    }
    expect(row('phone_keypad').value, '+372');
    expect(owner.commands, isEmpty);
    await tester.pumpWidget(const SizedBox());
    owner.state = PhoneCallState.active;
    await tester.pumpWidget(host(const ActiveCallPage()));
    await checkNativeHost(tester, 'real-native-active-call-dark');
    expect(row('call_segment_0').plainText, true);
    await row('call_mute').action!(null);
    await row('call_speaker').action!(null);
    expect(owner.commands, ['mute', 'speaker']);
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('native voice review keeps original goal, selection and navigation owners', (tester) async {
    await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
    addTearDown(JourneyHermeticBoot.stop);
    final io = FakeVoiceIO();
    final flow = GuidedVoiceController(io)
      ..promptIndex = 4
      ..stage = IntroductionStage.review;
    flow.answers.addAll([
      IntroductionAnswer('I build bicycles.', Uint8List(32000 * 6), 'memory'),
      IntroductionAnswer('Ship Omi', Uint8List(32000 * 6), 'goal',
          isGoal: true, originalText: 'Right now my number one goal is to ship Omi.'),
    ]);
    var backCount = 0;
    final parentRevision = ValueNotifier(0);
    await tester.pumpWidget(MultiProvider(
        providers: defaultAuditProviders(),
        child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: const [Locale('en')],
            theme: buildOmiTheme(brightness: Brightness.dark),
            home: ValueListenableBuilder<int>(
                valueListenable: parentRevision,
                builder: (context, revision, _) => Scaffold(
                    body: OnboardingStepLayout(
                        reserveHeader: true,
                        nativeNavigation: true,
                        nativeProgress: 'Step 5 of 6',
                        onBack: () => backCount++,
                        child: SpeechProfileWidget(controller: flow, goNext: () {}, onSkip: () {})))))));
    await checkNativeHost(tester, 'real-native-voice-review-dark');
    final initialSnapshot = tester.widget<UiKitView>(find.byType(UiKitView)).creationParams as Map;
    expect((initialSnapshot['toolbar'] as List).any((row) => row['id'] == 'onboarding_back'), true);
    final speechOwner = tester.state(find.byType(SpeechProfileWidget));
    final viewId = nativeViewId(tester, find.byType(UiKitView));
    parentRevision.value++;
    await tester.pump();
    await Future<void>.delayed(const Duration(milliseconds: 300));
    await tester.pump();
    expect(identical(tester.state(find.byType(SpeechProfileWidget)), speechOwner), true,
        reason: 'A parent rebuild must retain the capture/review owner');
    expect(nativeViewId(tester, find.byType(UiKitView)), viewId);
    expect(flow.answers.length, 2);
    NativeRow row(String id) => tester
        .widget<IosNativeSurface>(find.byType(IosNativeSurface))
        .sections
        .expand((section) => section.rows)
        .firstWhere((row) => row.id == id);
    final snapshot = tester.widget<UiKitView>(find.byType(UiKitView)).creationParams as Map;
    expect((snapshot['toolbar'] as List).any((row) => row['id'] == 'onboarding_back'), true);
    expect(backCount, 0);
    expect(io.uploads, isEmpty);
    expect(io.remembered, isEmpty);
    await row('voice_keep_memory').action!(false);
    await row('voice_text_goal_0').action!('Build native iOS screens');
    await tester.pump();
    expect(flow.answers.first.keep, false);
    expect(flow.answers.last.text, 'Build native iOS screens');
    await row('voice_original_goal').action!(null);
    await tester.pump();
    expect(flow.answers.last.editRevision, 1);
    expect(row('voice_text_goal_1').value, 'Right now my number one goal is to ship Omi.');
    expect(io.goals, isEmpty, reason: 'Editing never saves a goal');
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    flow.dispose();
    parentRevision.dispose();
    expect(tester.takeException(), isNull);
  });

  testWidgets('native phone setup keeps number validation and explicit verification ownership', (tester) async {
    await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
    addTearDown(JourneyHermeticBoot.stop);
    final owner = _NativePhoneOwner();
    await tester.pumpWidget(MultiProvider(
      providers: [...defaultAuditProviders(), ChangeNotifierProvider<PhoneCallProvider>.value(value: owner)],
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        theme: buildOmiTheme(brightness: Brightness.dark),
        home: const PhoneSetupNumberPage(),
      ),
    ));
    await checkNativeHost(tester, 'real-native-phone-number-dark');
    NativeRow row(String id) => tester
        .widget<IosNativeSurface>(find.byType(IosNativeSurface))
        .sections
        .expand((section) => section.rows)
        .firstWhere((row) => row.id == id);
    expect(row('phone_number_input').keyboard, 'phone');
    await row('phone_number_country').action!('EE');
    await row('phone_number_input').action!('5142537');
    await tester.pump();
    expect(row('phone_number_continue').enabled, true);
    expect(owner.verified, isEmpty);
    await row('phone_number_continue').action!(null);
    await tester.pump();
    expect(owner.verified, ['+3725142537']);
    expect(row('phone_number_error').title, isNotEmpty);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    owner.dispose();
  });

  testWidgets('People uses native filters and preserves selection rules', (tester) async {
    await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
    addTearDown(JourneyHermeticBoot.stop);
    final people = PeopleProvider(
        loadPeople: () async => PeopleListResponse(people: [
              Person(
                  id: 'ada',
                  name: 'Ada',
                  createdAt: DateTime(2026),
                  updatedAt: DateTime(2026),
                  pinned: true,
                  confidence: 'confirmed',
                  conversationCount: 8),
              Person(
                  id: 'sam',
                  name: 'Sam',
                  createdAt: DateTime(2026),
                  updatedAt: DateTime(2026),
                  confidence: 'unverified',
                  conversationCount: 2),
            ]));
    await tester.pumpWidget(MultiProvider(
      providers: [
        ...defaultAuditProviders(),
        ChangeNotifierProvider<PeopleProvider>.value(value: people),
        ChangeNotifierProvider(
            create: (_) => SpeakerTagPromptsProvider(
                fetchSettings: () => Completer<ApiResult<GeneratedVoiceProfileSettings>>().future)),
      ],
      child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          theme: buildOmiTheme(brightness: Brightness.dark),
          home: const UserPeoplePage()),
    ));
    await checkNativeHost(tester, 'real-native-people-dark');
    var surface = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
    final rows = surface.sections.expand((section) => section.rows);
    expect(rows.firstWhere((row) => row.id == 'person_ada').level, 3);
    await rows.firstWhere((row) => row.id == 'person_sam').action!('select');
    await tester.pump();
    surface = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
    final selecting = surface.sections.expand((section) => section.rows);
    expect(people.selectedIds, {'sam'});
    expect(selecting.firstWhere((row) => row.id == 'person_ada').enabled, false);
    expect(selecting.firstWhere((row) => row.id == 'person_sam').value, true);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    people.dispose();
  });

  testWidgets('real folder sheet contains native edit and color controls', (tester) async {
    await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
    addTearDown(JourneyHermeticBoot.stop);
    await tester.pumpWidget(MultiProvider(
      providers: defaultAuditProviders(),
      child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          theme: buildOmiTheme(brightness: Brightness.dark),
          home: Builder(
              builder: (context) => Scaffold(
                  body: TextButton(
                      onPressed: () => showOmiSheet<void>(
                          context: context,
                          title: 'New Folder',
                          builder: (_) => const CreateFolderBottomSheet(),
                          nativeBuilder: (_) => const CreateFolderBottomSheet(native: true)),
                      child: const Text('Open Folder'))))),
    ));
    await tester.tap(find.text('Open Folder'));
    await checkNativeHost(tester, 'real-native-folder-editor-dark');
    final surface = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
    final rows = surface.sections.single.rows;
    expect(rows.firstWhere((row) => row.id == 'folder_color').kind, 'color');
    await rows.firstWhere((row) => row.id == 'folder_name').action!('Trip notes');
    await rows.firstWhere((row) => row.id == 'folder_color').action!('#EF4444');
    await tester.pump();
    final updated = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface)).sections.single.rows;
    expect(updated.firstWhere((row) => row.id == 'folder_name').value, 'Trip notes');
    expect(updated.firstWhere((row) => row.id == 'folder_color').value, '#EF4444');
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('memory management retains native filters and existing provider', (tester) async {
    await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
    addTearDown(JourneyHermeticBoot.stop);
    await tester.pumpWidget(MultiProvider(
      providers: defaultAuditProviders(),
      child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          theme: buildOmiTheme(brightness: Brightness.dark),
          home: Builder(
              builder: (context) =>
                  Scaffold(body: MemoryManagementSheet(provider: context.read<MemoriesProvider>(), native: true)))),
    ));
    await checkNativeHost(tester, 'real-native-memory-management-dark');
    final surface = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
    await surface.sections
        .expand((section) => section.rows)
        .firstWhere((row) => row.id == 'memory_category_manual')
        .action!(true);
    await tester.pump();
    final updated = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
    expect(
        updated.sections
            .expand((section) => section.rows)
            .firstWhere((row) => row.id == 'memory_category_manual')
            .value,
        true);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    expect(tester.takeException(), isNull);
  });
  testWidgets('real Settings uses native navigation despite NEW and BETA labels', (tester) async {
    await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark', 'givenName': 'Ada'});
    addTearDown(JourneyHermeticBoot.stop);
    await tester.pumpWidget(MultiProvider(
      providers: defaultAuditProviders(),
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        theme: buildOmiTheme(brightness: Brightness.dark),
        home: Builder(
            builder: (context) => Scaffold(
                    body: TextButton(
                  onPressed: () => SettingsDrawer.show(context),
                  child: const Text('Open Settings'),
                ))),
      ),
    ));
    await tester.tap(find.text('Open Settings'));
    await tester.pump(const Duration(seconds: 2));
    await tester.pump(const Duration(seconds: 2));
    final native = find.byType(UiKitView);
    expect(native, findsOneWidget);
    final viewId = nativeViewId(tester, native);
    final snapshot = tester.widget<UiKitView>(native).creationParams as Map;
    expect(snapshot['appearance'], 'dark');
    expect(snapshot['largeTitle'], true);
    await MethodChannel('com.omi.native_ui/surface/$viewId').invokeMethod<void>('update', snapshot);
    expect(tester.takeException(), isNull);
    await Future<void>.delayed(const Duration(seconds: 2));
    await tester.pump();
    expect(await captureScreenshot('real-native-settings-dark'), isNotEmpty);
    final appearance = tester.element(find.byType(IosNativeSurface)).read<AppearanceProvider>();
    await appearance.setMode(ThemeMode.light);
    await tester.pump(const Duration(seconds: 2));
    await Future<void>.delayed(const Duration(seconds: 2));
    await tester.pump();
    expect(await captureScreenshot('real-native-settings-light'), isNotEmpty);
    await appearance.setMode(ThemeMode.system);
    await tester.pump(const Duration(seconds: 2));
    await Future<void>.delayed(const Duration(seconds: 2));
    await tester.pump();
    expect(
      await captureScreenshot('real-native-settings-system-${binding.platformDispatcher.platformBrightness.name}'),
      isNotEmpty,
    );
    await appearance.setMode(ThemeMode.dark);
    await tester.pump(const Duration(seconds: 2));
    tester.widget<IosNativeSurface>(find.byType(IosNativeSurface)).search!('permissions');
    await tester.pump(const Duration(seconds: 2));
    await Future<void>.delayed(const Duration(seconds: 2));
    await tester.pump();
    final search = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
    expect(search.sections.single.id, 'settings_search');
    expect(search.sections.single.rows, isNotEmpty);
    expect(await captureScreenshot('real-native-settings-search-dark'), isNotEmpty);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    expect(tester.takeException(), isNull);
  });
  testWidgets('native Home fills its Flutter host without splitting the scroll area', (tester) async {
    await JourneyHermeticBoot.start();
    addTearDown(JourneyHermeticBoot.stop);
    await tester.pumpWidget(MultiProvider(
      providers: defaultAuditProviders(),
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        theme: buildOmiTheme(brightness: Brightness.dark),
        home: Scaffold(
            body: IosNativeHome(
          requestInitialLoad: false,
          loadRecaps: () async => (
            ok: true,
            items: [
              DailySummary(
                id: 'host-recap',
                date: '2026-10-03',
                createdAt: DateTime.utc(2026, 10, 3),
                headline: 'A Busy Day of Shopping and Omi',
                overview: '',
                stats: DayStats(),
              )
            ]
          ),
          header: [
            NativeHomeAction('device', '53%', 'battery.75percent', () {}),
            NativeHomeAction('settings', 'Settings', 'gearshape', () {})
          ],
          footer: [
            NativeHomeAction('chat', 'Ask Omi', 'bubble.left', () {}),
            NativeHomeAction('tasks', 'Tasks', 'checklist', () {})
          ],
        )),
      ),
    ));
    await tester.pump(const Duration(seconds: 2));
    await tester.pump(const Duration(seconds: 2));
    final native = find.byType(UiKitView);
    expect(native, findsOneWidget);
    final frame = tester.getRect(native);
    expect(frame.width, greaterThan(300));
    expect(frame.height, greaterThan(650));
    final viewId = nativeViewId(tester, native);
    await MethodChannel('com.omi.native_ui/home/$viewId')
        .invokeMethod<void>('update', tester.widget<UiKitView>(native).creationParams);
    expect(tester.takeException(), isNull);
    final screenshot = await captureScreenshot('native-home-in-flutter-host');
    expect(screenshot, isNotEmpty);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
  });
  testWidgets('native form fills its Flutter host and detaches cleanly', (tester) async {
    await JourneyHermeticBoot.start();
    addTearDown(JourneyHermeticBoot.stop);
    await tester.pumpWidget(MultiProvider(
      providers: defaultAuditProviders(),
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(
            body: IosNativeSurface(
          title: 'Edit Task',
          fallback: const Text('Native renderer unavailable'),
          sections: [
            NativeSection('editor', [
              NativeRow('draft', 'Description', kind: 'text', value: 'Review the native iOS screens', action: (_) {}),
              NativeRow('complete', 'Completed', kind: 'toggle', value: false, action: (_) {}),
            ])
          ],
          toolbar: [NativeRow('save', 'Save', action: (_) {})],
        )),
      ),
    ));
    await tester.pump(const Duration(seconds: 2));
    await tester.pump(const Duration(seconds: 2));
    final native = find.byType(UiKitView);
    expect(native, findsOneWidget);
    expect(tester.getRect(native).height, greaterThan(650));
    final viewId = nativeViewId(tester, native);
    // A rejected native factory must fail this check instead of passing as an empty UIView.
    await MethodChannel('com.omi.native_ui/surface/$viewId')
        .invokeMethod<void>('update', tester.widget<UiKitView>(native).creationParams);
    expect(tester.takeException(), isNull);
    // UIKit drawing continues independently of the Flutter test frame.
    await Future<void>.delayed(const Duration(seconds: 2));
    await tester.pump();
    expect(await captureScreenshot('native-form-in-flutter-host'), isNotEmpty);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    expect(tester.takeException(), isNull);
  });
}
