import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_contacts/flutter_contacts.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nested/nested.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/test_prompts.dart';
import 'package:omi/pages/conversation_detail/widgets/audio_download_progress_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_detail_header.dart';
import 'package:omi/pages/conversation_detail/widgets/create_template_bottom_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/feedback_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/share_to_contacts_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/summarized_apps_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/summary_tab.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import 'native_test_host.dart';

class _EnvNoIntercom implements EnvFields {
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => null;
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

final _l10n = lookupAppLocalizations(const Locale('en'));
const _config = MethodChannel('com.omi.native_ui/config');
const _contacts = MethodChannel('flutter_contacts');

App _app(String id, String name, {String? uid, String description = 'Writes a summary'}) => App(
      id: id,
      name: name,
      author: 'tester',
      description: description,
      image: '/apps/$id.png',
      capabilities: {'memories'},
      status: 'approved',
      uid: uid,
      category: 'productivity',
      approved: true,
      ratingCount: 0,
      enabled: true,
      deleted: false,
      isPaid: false,
      isUserPaid: false,
    );

ServerConversation _conversation({ConversationVisibility visibility = ConversationVisibility.private_}) =>
    ServerConversation(
      id: 'conv-1',
      createdAt: DateTime(2026, 7, 1, 9).toUtc(),
      structured: Structured('Sprint sync', 'Short overview.'),
    )..visibility = visibility;

/// The template owner with fixed catalogs; records reprocessing, default changes and installs.
class _TemplateOwner extends ConversationDetailProvider {
  _TemplateOwner({
    this.suggested = const [],
    this.enabled = const [],
    this.preferred,
    this.lastUsed,
    this.unavailable = const {},
  });

  final List<App> suggested, enabled;
  final String? preferred, lastUsed;
  final Set<String> unavailable;
  final reprocessed = <String?>[];
  final defaults = <String>[];
  final install = Completer<bool>();

  @override
  List<App> get cachedSuggestedApps => suggested;
  @override
  List<App> get cachedEnabledConversationApps => enabled;
  @override
  Future<void> fetchAndCacheSuggestedApps() async {}
  @override
  Future<void> fetchAndCacheEnabledConversationApps() async {}
  @override
  String? get preferredSummarizationAppId => preferred;
  @override
  String? getLastUsedSummarizationAppId() => lastUsed;
  @override
  void trackLastUsedSummarizationApp(String appId) {}
  @override
  bool isSuggestedAppAvailable(String appId) => !unavailable.contains(appId);
  var installs = 0;
  @override
  Future<bool> enableApp(App app) {
    installs++;
    return install.future;
  }

  @override
  Future<bool> setPreferredSummarizationApp(String appId) async {
    defaults.add(appId);
    return true;
  }

  @override
  Future<bool> reprocessConversation({String? appId}) async {
    reprocessed.add(appId);
    return true;
  }
}

/// A detail owner whose app catalog is [known].
class _AttributionOwner extends ConversationDetailProvider {
  _AttributionOwner(this.known);

  final Map<String, App> known;

  @override
  App? findAppById(String? appId) => known[appId];
}

ConversationDetailProvider _detail(ConversationDetailProvider provider, ServerConversation conversation) {
  addTearDown(provider.dispose);
  provider.selectedDate = conversationLocalDayKey(conversation.createdAt);
  provider.setCachedConversation(conversation);
  return provider;
}

/// A page with an "open" button that pushes [sheet] as its own route, so a test sees it close.
Future<void> _open(WidgetTester tester, WidgetBuilder sheet, {List<SingleChildWidget> providers = const []}) async {
  await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AppearanceProvider(read: () => 'dark', write: (_) async {})),
        ...providers,
      ],
      child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: Builder(
              builder: (context) => Scaffold(
                  body: Center(
                      child: TextButton(
                          onPressed: () => Navigator.of(context)
                              .push(MaterialPageRoute<void>(builder: (context) => Scaffold(body: sheet(context)))),
                          child: const Text('open'))))))));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

IosNativeSurface _surface(WidgetTester tester) => tester.widget(find.byType(IosNativeSurface).last);

List<NativeRow> _rows(WidgetTester tester) =>
    [..._surface(tester).toolbar, ..._surface(tester).sections.expand((section) => section.rows)];

NativeRow _row(WidgetTester tester, String id) => _rows(tester).singleWhere((row) => row.id == id);

bool _hasRow(WidgetTester tester, String id) => _rows(tester).any((row) => row.id == id);

/// Answers each native confirmation with [reply], as Swift's presenter would.
void _answerConfirmations(String reply) {
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(_config, (call) async {
    if (call.method != 'present') return null;
    return {'action': reply, 'values': <String, Object?>{}};
  });
  addTearDown(() => messenger.setMockMethodCallHandler(_config, null));
}

/// The fixed order product chose for each population, spelled out so a reorder fails here.
const _reasonOrder = {
  FeedbackReasonPopulation.summary: [
    'feedback_reason_summaryInaccurate',
    'feedback_reason_summaryIncomplete',
    'feedback_reason_summaryIrrelevant',
    'feedback_reason_summaryWrongContext',
    'feedback_reason_summaryOther',
  ],
  FeedbackReasonPopulation.recording: [
    'feedback_reason_recordingMissingAudio',
    'feedback_reason_recordingPoorTranscription',
    'feedback_reason_recordingWrongSpeaker',
    'feedback_reason_recordingDelayedOrStuck',
    'feedback_reason_recordingFragmentedOrDuplicated',
    'feedback_reason_recordingOther',
  ],
};

void main() {
  setUpAll(() => Env.init(_EnvNoIntercom()));

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  group('feedback reason sheet', () {
    Future<List<(int, MobileFeedbackReason?)>> openFeedback(
        WidgetTester tester, FeedbackReasonPopulation population) async {
      final submitted = <(int, MobileFeedbackReason?)>[];
      await _open(
          tester,
          (_) => FeedbackReasonNativeSheet(
              title: _l10n.wasThisHelpful,
              population: population,
              onSubmit: (value, reason) => submitted.add((value, reason))));
      return submitted;
    }

    testWidgets('each reason submits -1 with that reason once and closes, in the fixed order', (tester) async {
      NativeTestHost.install();
      for (final population in FeedbackReasonPopulation.values) {
        final reasons = feedbackReasonsFor(population);
        for (final reason in reasons) {
          final submitted = await openFeedback(tester, population);
          expect(_surface(tester).sections.first.rows.map((row) => row.id), _reasonOrder[population]);
          expect(_row(tester, 'feedback_reason_${reason.name}').title, feedbackReasonLabel(_l10n, reason));
          await _row(tester, 'feedback_reason_${reason.name}').action!(null);
          await tester.pumpAndSettle();
          expect(submitted, [(-1, reason)]);
          expect(find.byType(FeedbackReasonNativeSheet), findsNothing);
        }
      }
    });

    testWidgets('All good submits +1 without a reason', (tester) async {
      NativeTestHost.install();
      final submitted = await openFeedback(tester, FeedbackReasonPopulation.summary);
      expect(_row(tester, 'feedback_all_good').symbol, 'hand.thumbsup');
      await _row(tester, 'feedback_all_good').action!(null);
      await tester.pumpAndSettle();
      expect(submitted, [(1, null)]);
      expect(find.byType(FeedbackReasonNativeSheet), findsNothing);
    });

    testWidgets('Chat with us is absent while Intercom is disabled; closing submits nothing', (tester) async {
      NativeTestHost.install();
      final submitted = await openFeedback(tester, FeedbackReasonPopulation.recording);
      expect(_hasRow(tester, 'feedback_chat_with_us'), isFalse);
      expect(_rows(tester).every((row) => row.valid), isTrue);
      await _row(tester, 'feedback_close').action!(null);
      await tester.pumpAndSettle();
      expect(find.byType(FeedbackReasonNativeSheet), findsNothing);
      expect(submitted, isEmpty);
    });
  });

  group('summary template chooser', () {
    final suggestedApp = _app('suggested', 'Suggested');
    final defaultApp = _app('default', 'Zulu default');
    final lastUsedApp = _app('last', 'Yankee last');
    final ownApp = _app('own', 'X-ray own', uid: 'me');
    final alpha = _app('alpha', 'alpha');
    final bravo = _app('bravo', 'Bravo');

    Future<_TemplateOwner> openChooser(WidgetTester tester,
        {Set<String> unavailable = const {}, String lastUsed = 'last'}) async {
      NativeTestHost.install();
      SharedPreferencesUtil().uid = 'me';
      final owner = _detail(
          _TemplateOwner(
              suggested: [suggestedApp],
              // The suggested and last used apps also appear among the enabled ones.
              enabled: [bravo, suggestedApp, alpha, ownApp, lastUsedApp, defaultApp],
              preferred: 'default',
              lastUsed: lastUsed,
              unavailable: unavailable),
          _conversation()) as _TemplateOwner;
      await _open(tester, (_) => const SummarizedAppsBottomSheet(native: true), providers: [
        ChangeNotifierProvider<ConversationDetailProvider>.value(value: owner),
        ChangeNotifierProvider(create: (_) => AppProvider()),
      ]);
      return owner;
    }

    testWidgets('keeps the classic order: suggested, default, last used, own apps, then A-Z', (tester) async {
      await openChooser(tester);
      final sections = _surface(tester).sections;
      expect(sections.map((section) => section.id), ['template_suggested', 'template_other', 'template_creative']);
      expect(sections[0].title, _l10n.suggestedTemplates);
      expect(sections[1].title, _l10n.otherTemplates);
      final apps = sections.take(2).expand((section) => section.rows).toList();
      expect(apps.map((row) => row.id), [for (var i = 0; i < 6; i++) 'template_app:$i']);
      expect(apps.map((row) => row.title), ['Suggested', 'Zulu default', 'Yankee last', 'X-ray own', 'alpha', 'Bravo']);
      expect(apps[1].subtitle, contains(_l10n.defaultLabel));
      expect(apps[2].subtitle, contains(_l10n.lastUsedLabel));
      expect(apps.every((row) => row.kind == 'navigation' && row.valid), isTrue);
      expect(apps.first.imageUri, startsWith('https://'));
      expect(apps.first.options, {'default': _l10n.setDefaultButton});
      expect(sections[2].rows.map((row) => row.id), ['template_create', 'template_all']);
    });

    testWidgets('a suggested template used last keeps its Last used badge on its one row', (tester) async {
      await openChooser(tester, lastUsed: 'suggested');
      final apps = _surface(tester).sections.take(2).expand((section) => section.rows).toList();
      expect(apps.map((row) => row.title), ['Suggested', 'Zulu default', 'X-ray own', 'alpha', 'Bravo', 'Yankee last']);
      expect(apps.first.subtitle, contains(_l10n.lastUsedLabel));
      expect(apps.skip(1).any((row) => row.subtitle.contains(_l10n.lastUsedLabel)), isFalse);
    });

    testWidgets('a tap reprocesses with that app once and closes', (tester) async {
      final owner = await openChooser(tester);
      await _row(tester, 'template_app:4').action!(null);
      await tester.pumpAndSettle();
      expect(owner.reprocessed, ['alpha']);
      expect(find.byType(SummarizedAppsBottomSheet), findsNothing);
    });

    testWidgets('Set Default asks first and saves only after confirmation', (tester) async {
      final owner = await openChooser(tester);
      _answerConfirmations('cancel');
      await _row(tester, 'template_app:4').action!('default');
      await tester.pumpAndSettle();
      expect(owner.defaults, isEmpty);

      _answerConfirmations('confirm');
      await _row(tester, 'template_app:4').action!('default');
      await tester.pumpAndSettle();
      expect(owner.defaults, ['alpha']);
      expect(owner.reprocessed, isEmpty);
    });

    testWidgets('an installing template is locked until its install finishes', (tester) async {
      final owner = await openChooser(tester, unavailable: {'suggested'});
      unawaited(Future.sync(() => _row(tester, 'template_app:0').action!(null)));
      await tester.pump();
      final locked = _row(tester, 'template_app:0');
      expect(locked.enabled, isFalse);
      expect(locked.projection['enabled'], isFalse);
      expect(locked.subtitle, _l10n.installingApp);
      // A second tap while installing starts nothing.
      unawaited(Future.sync(() => _row(tester, 'template_app:0').action!(null)));
      await tester.pump();
      expect(owner.installs, 1);

      // A failed install unlocks the row and keeps the sheet open.
      owner.install.complete(false);
      await tester.pumpAndSettle();
      expect(_row(tester, 'template_app:0').projection['enabled'], isTrue);
      expect(owner.reprocessed, isEmpty);
    });
  });

  group('summary attribution', () {
    final writer = _app('writer', 'Meeting notes', description: 'Turns calls into notes');

    Future<List<NativeRow>> summaryRows(WidgetTester tester, Map<String, App> known) async {
      NativeTestHost.install();
      final conversation = ServerConversation(
        id: 'conv-app',
        createdAt: DateTime(2026, 7, 1, 9).toUtc(),
        structured: Structured('Sprint sync', ''),
        appResults: [AppResponse('Decided to ship Friday.', appId: 'writer')],
        // Still processing, so the summary projects without the completed-only extras.
        status: ConversationStatus.processing,
      );
      final owner = _detail(_AttributionOwner(known), conversation);
      final published = <List<NativeSection>>[];
      await tester.pumpWidget(MultiProvider(
          providers: [ChangeNotifierProvider<ConversationDetailProvider>.value(value: owner)],
          child: MaterialApp(
              localizationsDelegates: AppLocalizations.localizationsDelegates,
              supportedLocales: const [Locale('en')],
              home: Scaffold(body: SummaryTab(onNativePresentation: published.add)))));
      await tester.pump();
      return published.last.single.rows;
    }

    testWidgets('an app-written summary names its app in a row that opens the app', (tester) async {
      final rows = await summaryRows(tester, {'writer': writer});
      final app = rows.singleWhere((row) => row.id == 'detail_summary_app');
      expect(app.title, 'Meeting notes');
      expect(app.kind, 'navigation');
      expect(app.subtitle, 'Turns calls into notes');
      expect(app.imageUri, startsWith('https://'));
      expect(app.action, isNotNull);
      expect(rows.every((row) => row.valid), isTrue);
    });

    testWidgets('an app the catalog no longer knows shows no attribution', (tester) async {
      final rows = await summaryRows(tester, {});
      expect(rows.map((row) => row.id), contains('detail_summary_content'));
      expect(rows.any((row) => row.id == 'detail_summary_app'), isFalse);
    });
  });

  group('create template', () {
    testWidgets('re-checks the name and prompt lengths in Dart before creating', (tester) async {
      NativeTestHost.install();
      await _open(tester, (_) => const CreateTemplateBottomSheet(conversationId: 'conv-1', native: true));
      expect(_row(tester, 'template_name').maximumLength, 100);
      expect(_row(tester, 'template_prompt').maximumLength, 10000);
      expect(_row(tester, 'template_public').value, isFalse);
      expect(_row(tester, 'template_form_create').title, _l10n.createApp);
      expect(_hasRow(tester, 'template_validation'), isFalse);

      await _row(tester, 'template_form_create').action!(null);
      await tester.pump();
      expect(_row(tester, 'template_validation').title, _l10n.pleaseEnterAppName);

      await _row(tester, 'template_name').action!('ab');
      await tester.pump();
      expect(_row(tester, 'template_validation').title, _l10n.nameMustBeAtLeast3Characters);

      await _row(tester, 'template_name').action!('Standup');
      await tester.pump();
      expect(_row(tester, 'template_validation').title, _l10n.pleaseEnterAppPrompt);
      await _row(tester, 'template_prompt').action!('too short');
      await tester.pump();
      expect(_row(tester, 'template_validation').title, _l10n.promptMustBeAtLeast10Characters);

      await _row(tester, 'template_prompt').action!('List the decisions and owners.');
      await _row(tester, 'template_public').action!(true);
      await tester.pump();
      expect(_hasRow(tester, 'template_validation'), isFalse);
      expect(_row(tester, 'template_public').subtitle, _l10n.anyoneCanDiscoverTemplate);
      expect(_rows(tester).every((row) => row.valid), isTrue);
    });
  });

  group('visibility', () {
    Future<(ConversationDetailProvider, List<String>)> openVisibility(WidgetTester tester,
        {required ConversationVisibility current, bool saves = true}) async {
      NativeTestHost.install();
      final conversation = _conversation(visibility: current);
      final provider = _detail(ConversationDetailProvider(), conversation);
      final events = <String>[];
      await tester.pumpWidget(MultiProvider(
          providers: [
            ChangeNotifierProvider(create: (_) => AppearanceProvider(read: () => 'dark', write: (_) async {})),
            ChangeNotifierProvider<ConversationDetailProvider>.value(value: provider),
          ],
          child: MaterialApp(
              localizationsDelegates: AppLocalizations.localizationsDelegates,
              supportedLocales: const [Locale('en')],
              home: Builder(builder: (context) {
                final choose = ConversationVisibilitySheet.chooser(context, conversation,
                    setVisibility: (id, visibility) async {
                      events.add('set:$id:$visibility');
                      return saves;
                    },
                    share: (conversation) => events.add('share:${conversation.id}'));
                return Scaffold(
                    body: TextButton(
                        onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
                            builder: (routeContext) => Scaffold(
                                body: ConversationVisibilitySheet.native(routeContext, conversation, choose)))),
                        child: const Text('open')));
              }))));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      return (provider, events);
    }

    testWidgets('choosing the current value only closes', (tester) async {
      final (provider, events) = await openVisibility(tester, current: ConversationVisibility.private_);
      expect(_row(tester, 'visibility_private').symbol, 'checkmark.circle.fill');
      expect(_row(tester, 'visibility_shared').symbol, 'globe');
      expect(_row(tester, 'visibility_shared').subtitle, _l10n.anyoneWithLinkCanView);
      await _row(tester, 'visibility_private').action!(null);
      await tester.pumpAndSettle();
      expect(find.byType(IosNativeSurface), findsNothing);
      expect(events, isEmpty);
      expect(provider.conversation.visibility, ConversationVisibility.private_);
    });

    testWidgets('choosing Shared saves it and then shares the link', (tester) async {
      final (provider, events) = await openVisibility(tester, current: ConversationVisibility.private_);
      await _row(tester, 'visibility_shared').action!(null);
      await tester.pumpAndSettle();
      expect(events, ['set:conv-1:shared', 'share:conv-1']);
      expect(provider.conversation.visibility, ConversationVisibility.shared);
      expect(find.byType(IosNativeSurface), findsNothing);
    });

    testWidgets('a failed save reverts the visibility and shares nothing', (tester) async {
      final (provider, events) = await openVisibility(tester, current: ConversationVisibility.private_, saves: false);
      await _row(tester, 'visibility_shared').action!(null);
      await tester.pumpAndSettle();
      expect(events, ['set:conv-1:shared']);
      expect(provider.conversation.visibility, ConversationVisibility.private_);
    });
  });

  group('audio download', () {
    IosNativeSurface audioSurface(WidgetTester tester, AudioDownloadState state, double progress,
            {VoidCallback? onCancel}) =>
        AudioDownloadNativeSheet(state: state, progress: progress, onCancel: onCancel, fallback: const SizedBox())
            .build(tester.element(find.byType(Scaffold).last)) as IosNativeSurface;

    testWidgets('progress is a valid, clamped fraction with its percentage', (tester) async {
      await _open(tester, (_) => const SizedBox());
      for (final (input, expected, percent) in [(0.0, 0.0, ''), (0.5, 0.5, '50%'), (1.0, 1.0, '100%')]) {
        final row = audioSurface(tester, AudioDownloadState.downloading, input)
            .sections
            .single
            .rows
            .singleWhere((row) => row.id == 'audio_download_progress');
        expect((row.value, row.subtitle, row.valid), (expected, percent, true));
      }
      for (final (input, expected) in [(double.nan, 0.0), (double.infinity, 0.0), (-0.2, 0.0), (1.7, 1.0)]) {
        final row = audioSurface(tester, AudioDownloadState.downloading, input)
            .sections
            .single
            .rows
            .singleWhere((row) => row.id == 'audio_download_progress');
        expect(row.valid, isTrue, reason: '$input');
        expect(row.value, expected);
      }
      final done = audioSurface(tester, AudioDownloadState.success, 1).sections.single.rows;
      expect(done.map((row) => (row.id, row.symbol)), [('audio_download_status', 'checkmark.circle.fill')]);
      final failed = audioSurface(tester, AudioDownloadState.error, 0).sections.single.rows;
      expect(failed.single.title, _l10n.audioShareFailed);
    });

    testWidgets('Cancel runs onCancel once and closes the sheet', (tester) async {
      NativeTestHost.install();
      await _open(tester, (_) => const SizedBox());
      var cancelled = 0;
      final handle = AudioDownloadSheetHandle.show(tester.element(find.byType(Scaffold).last),
          onCancel: () => cancelled++, nativeContentForTest: true);
      await tester.pump(const Duration(seconds: 1));
      expect(handle.isOpen, isTrue);
      expect(_surface(tester).loading, isTrue, reason: 'Preparing shows the activity row');
      final cancel = _row(tester, 'audio_download_cancel');
      expect(cancel.destructive, isTrue);
      await cancel.action!(null);
      await cancel.action!(null);
      await tester.pump(const Duration(seconds: 1));
      expect(cancelled, 1);
      expect(handle.isOpen, isFalse);
      expect(find.byType(AudioDownloadNativeSheet), findsNothing);
    });

    testWidgets('a close before the sheet first builds still closes it', (tester) async {
      await _open(tester, (_) => const SizedBox());
      final handle = AudioDownloadSheetHandle.show(tester.element(find.byType(Scaffold).last));
      handle.close();
      for (var frame = 0; frame < 4; frame++) {
        await tester.pump(const Duration(milliseconds: 500));
      }
      expect(handle.isOpen, isFalse);
      expect(find.byType(AudioDownloadProgressSheet), findsNothing);
    });
  });

  group('share via SMS', () {
    setUp(() {
      final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockMethodCallHandler(_contacts, (call) async {
        if (call.method == 'permissions.request') return 'granted';
        if (call.method == 'crud.getAll') {
          return [
            const Contact(id: 'b', displayName: 'Bea', phones: [Phone(number: '514 2537')]).toJson(),
            const Contact(id: 'a', displayName: 'Avery', phones: [Phone(number: '+1 (415) 555-0100')]).toJson(),
          ];
        }
        return null;
      });
      addTearDown(() => messenger.setMockMethodCallHandler(_contacts, null));
    });

    testWidgets('Share is disabled until a contact is selected, and search matches names and numbers', (tester) async {
      NativeTestHost.install();
      final conversation = _conversation();
      await _open(tester, (_) => ShareToContactsBottomSheet(conversation: conversation, native: true), providers: [
        ChangeNotifierProvider<ConversationDetailProvider>.value(
            value: _detail(ConversationDetailProvider(), conversation)),
      ]);
      expect(_surface(tester).loading, isFalse);
      final share = _row(tester, 'contacts_share');
      expect((share.title, share.enabled, share.projection['enabled']), (_l10n.selectContactsToShare, false, false));
      expect(_hasRow(tester, 'contacts_clear'), isFalse);
      expect(_row(tester, 'contact:0').title, 'Avery');
      expect(_row(tester, 'contact:0').subtitle, '+14155550100');

      await _row(tester, 'contact:1').action!(true);
      await tester.pump();
      expect(_row(tester, 'contact:1').value, isTrue);
      expect(_row(tester, 'contacts_share').title, _l10n.shareWithContactCount(1));
      expect(_row(tester, 'contacts_share').projection['enabled'], isTrue);
      expect(_hasRow(tester, 'contacts_clear'), isTrue);

      await _surface(tester).search!('bea');
      await tester.pump();
      expect(_surface(tester).sections.last.rows.map((row) => row.title), ['Bea']);
      await _surface(tester).search!('4155');
      await tester.pump();
      expect(_surface(tester).sections.last.rows.map((row) => row.title), ['Avery']);
      await _surface(tester).search!('nobody');
      await tester.pump();
      expect(_surface(tester).sections.last.rows.single.title, _l10n.noContactsMatchSearch);

      await _row(tester, 'contacts_clear').action!(null);
      await tester.pump();
      expect(_row(tester, 'contacts_share').projection['enabled'], isFalse);
      expect(_rows(tester).every((row) => row.valid), isTrue);
    });
  });

  group('test prompt', () {
    testWidgets('sends the prompt once and shows the result without bold markers', (tester) async {
      NativeTestHost.install();
      final sent = <(String, String)>[];
      final reply = Completer<String>();
      await _open(
          tester,
          (_) => TestPromptsPage(
              conversation: _conversation(),
              runPrompt: (prompt, id) {
                sent.add((prompt, id));
                return reply.future;
              }));
      expect(_row(tester, 'test_prompt_input').maximumLength, 10000);
      await _row(tester, 'test_prompt_input').action!('Summarize the risks');
      await tester.pump();
      unawaited(Future.sync(() => _row(tester, 'test_prompt_send').action!(null)));
      await tester.pump();
      expect(_row(tester, 'test_prompt_send').projection['enabled'], isFalse);
      unawaited(Future.sync(() => _row(tester, 'test_prompt_send').action!(null)));
      await tester.pump();

      reply.complete('**Risk**: the launch date');
      await tester.pumpAndSettle();
      expect(sent, [('Summarize the risks', 'conv-1')]);
      expect(_row(tester, 'test_prompt_result').title, 'Risk: the launch date');
      expect(_row(tester, 'test_prompt_send').projection['enabled'], isTrue);
    });
  });
}
