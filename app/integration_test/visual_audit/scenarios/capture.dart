// Home's capture surfaces where the app really draws them: the live card at the top of Home, the
// record button to the right of the Ask Omi bar above the tab bar, the device chip in the header,
// the sheets they open, and the live page. The frame mirrors HomePage's layout; its Ask Omi bar
// is a copy of HomePage._buildChatBar (private there).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/pages/conversations/widgets/daily_summaries_list.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:nested/nested.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/pages/home/home_content.dart';
import 'package:omi/pages/home/widgets/battery_info_widget.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/widgets/bottom_nav_bar.dart';
import 'package:omi/widgets/header_circle_button.dart';

import '../fakes.dart';
import '../harness.dart';

enum AuditLive { idle, pendant, pendantPaused, phone, phonePaused, phoneAfterPendant }

/// A capture provider reporting one fixed live state, with a short transcript.
class AuditCaptureProvider extends ChangeNotifier implements CaptureProvider {
  AuditCaptureProvider(this.live);
  final AuditLive live;

  bool get _pendant => live == AuditLive.pendant || live == AuditLive.pendantPaused;
  bool get _phone => !_pendant && live != AuditLive.idle;

  @override
  String? get liveCaptureSource => _pendant ? 'omi' : (_phone ? 'phone' : null);
  @override
  RecordingState get recordingState => switch (live) {
        AuditLive.idle => RecordingState.stop,
        AuditLive.pendant => RecordingState.deviceRecord,
        AuditLive.pendantPaused || AuditLive.phonePaused => RecordingState.pause,
        _ => RecordingState.record,
      };
  @override
  bool get havingRecordingDevice => _pendant || live == AuditLive.phoneAfterPendant;
  @override
  BtDevice? get recordingDevice => havingRecordingDevice ? auditPendant : null;
  @override
  bool get isPaused => live == AuditLive.pendantPaused || live == AuditLive.phonePaused;
  @override
  bool get isPhoneMicPaused => live == AuditLive.phonePaused;
  @override
  bool get pendantPausedForPhone => live == AuditLive.phoneAfterPendant;
  @override
  bool get isCallActive => false;
  @override
  bool get isPhoneMicBatchRecording => false;
  @override
  bool get isPendantBatchRecording => false;
  @override
  DateTime? get liveCaptureStartedAt =>
      live == AuditLive.idle ? null : DateTime.now().subtract(Duration(seconds: _phone ? 134 : 724));
  @override
  String? get activeCaptureSessionId => live == AuditLive.idle ? null : 'live-audit';
  @override
  List<TranscriptSegment> get segments => live == AuditLive.idle
      ? []
      : [
          TranscriptSegment(
              id: 's1',
              text: 'So the plan is to ship the recording changes on Friday.',
              speaker: 'SPEAKER_0',
              isUser: true,
              personId: null,
              start: 0,
              end: 4,
              translations: []),
          TranscriptSegment(
              id: 's2',
              text: 'And let us keep the pendant flow exactly as it is.',
              speaker: 'SPEAKER_1',
              isUser: false,
              personId: null,
              start: 4,
              end: 9,
              translations: []),
        ];
  @override
  List<ConversationPhoto> get photos => const [];
  @override
  int? get offlineRecordingStartedAt => null;
  @override
  Duration? get customSttBufferingDuration => null;
  @override
  MessageServiceStatusEvent? get terminalTranscriptionFailure => null;
  @override
  bool get recordingDeviceServiceReady => true;
  @override
  bool get transcriptServiceReady => true;
  @override
  List<MessageEvent> get transcriptionServiceStatuses => const [];
  @override
  bool get isConversationMarkedForStarring => false;
  @override
  List<String> get taggingSegmentIds => const [];
  @override
  int get segmentsPhotosVersion => 1;
  @override
  String? get topConversationId => null;
  @override
  List<Wal> get unsyncedSessionWals => const [];
  @override
  int get inFlightAudioSeconds => 0;
  // Capture actions a tap may reach; the audit shows the screen the tap leads to, it does not
  // capture audio.
  @override
  Future<void> streamRecording({bool resumeCapture = true}) async {}
  @override
  Future<bool> stopStreamRecording({String reason = 'user_stopped', bool resumeHandedOffPendant = true}) async => true;
  @override
  Future<void> finishCapture() async {}
  @override
  Future<void> pauseCapture() async {}
  @override
  Future<void> resumeCapture() async {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _CallInProgress extends ChangeNotifier implements PhoneCallProvider {
  @override
  PhoneCallState get callState => PhoneCallState.active;
  @override
  Duration get callDuration => const Duration(minutes: 3, seconds: 10);
  @override
  List<TranscriptSegment> get transcriptSegments => [
        TranscriptSegment(
            id: 'c1',
            text: 'Thanks for calling back, I have the quote ready.',
            speaker: 'SPEAKER_1',
            isUser: false,
            personId: null,
            start: 0,
            end: 4,
            translations: []),
      ];
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

final auditPendant = BtDevice(id: 'd1', name: 'Omi Device', type: DeviceType.omi, rssi: -40);

/// Home as HomePage lays it out (Rev 3): header (device chip; Search and Settings), content, and the
/// dock with the round Ask button.
class _HomeFrame extends StatelessWidget {
  const _HomeFrame({this.fetchSummaries});

  final DailySummariesFetcher? fetchSummaries;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(
        automaticallyImplyLeading: false,
        backgroundColor: Theme.of(context).colorScheme.surface,
        titleSpacing: NavigationToolbar.kMiddleSpacing - (kMinTapTarget - kHeaderCircleDiameter) / 2,
        title: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          const Padding(
            padding: EdgeInsets.only(left: (kMinTapTarget - kHeaderCircleDiameter) / 2),
            child: BatteryInfoWidget(),
          ),
          Row(mainAxisSize: MainAxisSize.min, children: [
            HeaderCircleButton(
              semanticLabel: 'Search',
              onTap: () {},
              icon: OmiGlyph(OmiGlyphs.magnifyingGlass, size: 20, color: OmiColors.textPrimary),
            ),
            const SizedBox(width: 2),
            HeaderCircleButton(
              semanticLabel: 'Settings',
              onTap: () {},
              icon: OmiGlyph(OmiGlyphs.person, size: 20, color: OmiColors.textPrimary),
            ),
          ]),
        ]),
      ),
      body: Stack(children: [
        HomeContentPage(fetchSummaries: fetchSummaries),
        BottomNavBar(onTabTap: (_, __) {}, onAskTap: () {}),
      ]),
    );
  }
}

Future<void> _runHome(
  AuditRun a,
  AuditLive live, {
  bool pendantConnected = false,
  bool call = false,
  Finder? tap,
  Finder? longPress,
  String action = 'Home',
  bool withData = false,
  bool scroll = false,
}) async {
  await a.pump(_HomeFrame(fetchSummaries: withData ? _seededRecap : null), scaffold: false, providers: [
    if (withData) ...await _seededHomeData(a),
    ChangeNotifierProvider<DeviceProvider>.value(
        value: pendantConnected
            ? AuditDeviceProvider(connected: true, battery: 72, device: auditPendant)
            : AuditDeviceProvider()),
    ChangeNotifierProvider<CaptureProvider>.value(value: AuditCaptureProvider(live)),
    if (call) ChangeNotifierProvider<PhoneCallProvider>.value(value: _CallInProgress()),
  ]);
  if (tap != null) await a.tap(tap);
  if (longPress != null) await a.longPress(longPress);
  if (scroll) {
    // The Home list, top to bottom (the page's own scroll view, not the header's).
    await a.scrollSeries(action,
        scrollable: find.descendant(of: find.byType(HomeContentPage), matching: find.byType(Scrollable)).first);
    return;
  }
  await a.shot(action);
}

Future<void> _runLivePage(AuditRun a, AuditLive live) async {
  await a.pump(const ConversationCapturingPage(), scaffold: false, providers: [
    ChangeNotifierProvider<CaptureProvider>.value(value: AuditCaptureProvider(live)),
    if (live == AuditLive.pendant || live == AuditLive.pendantPaused)
      ChangeNotifierProvider<DeviceProvider>.value(
          value: AuditDeviceProvider(connected: true, battery: 72, device: auditPendant)),
  ]);
  await a.shot('The live page');
}

const _home = 'lib/pages/home/page.dart (Home: live or idle card, device chip, Search)';

/// A day's worth of Home: five conversations, three open tasks (one due today) and yesterday's
/// recap, as v2 Main shows them.
Future<List<SingleChildWidget>> _seededHomeData(AuditRun a) async {
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  ServerConversation conversation(
          String id, String title, String overview, ConversationSource source, int hour, int minute) =>
      ServerConversation(
        id: id,
        createdAt: today.add(Duration(hours: hour, minutes: minute)),
        startedAt: today.add(Duration(hours: hour, minutes: minute)),
        finishedAt: today.add(Duration(hours: hour, minutes: minute + 2)),
        structured: Structured(title, overview, emoji: '', category: 'work'),
        status: ConversationStatus.completed,
        source: source,
      );
  final conversations = ConversationProvider(
    conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
    isSignedIn: () => true,
  )
    ..conversations = [
      conversation('c1', 'Call Chitapa reminder', 'A note to yourself to call Chitapa before the end of the day.',
          ConversationSource.omi, 15, 14),
      conversation('c2', 'App reliability and subscription concerns',
          'Paying users are sometimes blocked; plan limits and failed payments.', ConversationSource.phone, 14, 43),
      conversation('c3', 'App UX and battery', 'Users complain about battery drain after the update.',
          ConversationSource.omi, 14, 42),
      conversation('c4', 'Pricing review', 'Leaning annual with a free tier.', ConversationSource.openglass, 11, 5),
      conversation('c5', 'iPhone roadmap', 'Capture and conversations first.', ConversationSource.omi, 9, 40),
    ]
    ..groupConversationsByDate();
  Future<ActionItemsResponse?> tasks({
    int limit = 100,
    int offset = 0,
    bool? completed,
    String? conversationId,
    DateTime? startDate,
    DateTime? endDate,
    DateTime? dueStartDate,
    DateTime? dueEndDate,
  }) async =>
      ActionItemsResponse(actionItems: [
        ActionItemWithMetadata(
          id: 't1',
          description: 'Call Chitapa',
          completed: false,
          dueAt: today.add(const Duration(hours: 17)),
          conversationId: 'c1',
        ),
        const ActionItemWithMetadata(
            id: 't2', description: 'Check the battery-drain reports', completed: false, conversationId: 'c3'),
        const ActionItemWithMetadata(id: 't3', description: 'Send the pricing draft', completed: false),
      ]);
  final actionItems = ActionItemsProvider(getActionItems: tasks);
  await a.tester.runAsync(actionItems.ensureLoaded);
  return [
    ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
    ChangeNotifierProvider<ActionItemsProvider>.value(value: actionItems),
  ];
}

Future<({List<DailySummary> items, bool ok})> _seededRecap({int limit = 20, int offset = 0}) async {
  final yesterday = DateTime.now().subtract(const Duration(days: 1));
  final date =
      '${yesterday.year}-${yesterday.month.toString().padLeft(2, '0')}-${yesterday.day.toString().padLeft(2, '0')}';
  return (
    items: [
      DailySummary(
        id: 'recap-1',
        date: date,
        createdAt: yesterday,
        headline: 'A planning day: pricing, the iPhone roadmap and two follow-ups.',
        overview: 'Pricing is leaning annual; the iOS roadmap puts capture first.',
        stats: DayStats(totalConversations: 6, totalDurationMinutes: 72, actionItemsCount: 5),
      ),
    ],
    ok: true,
  );
}

const _live = 'lib/pages/conversation_capturing/page.dart (ConversationCapturingPage)';

final captureScenarios = <AuditScenario>[
  AuditScenario(
    id: 'home-header',
    title: 'Home, nothing recording, pendant connected',
    page: _home,
    state: 'An Omi pendant connected at 72% battery; nothing recording',
    run: (a) => _runHome(a, withData: true, AuditLive.idle, pendantConnected: true),
  ),
  AuditScenario(
    id: 'home-first-day',
    title: 'Home on the first day: Welcome, Not listening, Getting started, Good to know',
    page: _home,
    state: 'A new account: no conversations, no device, nothing recording',
    run: (a) => _runHome(a, AuditLive.idle, scroll: true, action: 'Open Home on the first day'),
  ),
  AuditScenario(
    id: 'home-first-day-listening',
    title: 'Home on the first day while Omi listens',
    page: _home,
    state: 'A new account: no conversations; the pendant is recording',
    run: (a) => _runHome(a, AuditLive.pendant, pendantConnected: true, action: 'Omi is listening on the first day'),
  ),
  AuditScenario(
    id: 'home-main',
    title: 'Home with a day of conversations: live card, recap, conversations, up next',
    page: _home,
    state: 'The pendant recording at 72%; five conversations today, three open tasks, yesterday\'s recap',
    run: (a) => _runHome(a, AuditLive.pendant,
        pendantConnected: true, withData: true, scroll: true, action: 'Home on a normal day'),
  ),
  AuditScenario(
    id: 'home-capture-idle',
    title: 'Home, nothing recording, no device: Not listening, Start listening',
    page: _home,
    state: 'No device; nothing recording',
    run: (a) => _runHome(a, withData: true, AuditLive.idle),
  ),
  AuditScenario(
    id: 'home-recording-from',
    title: 'Recording from: the device chip opens the sources, one live at a time',
    page: 'lib/pages/devices/recording_source_sheet.dart (showRecordingSourceSheet)',
    state: 'An Omi pendant connected at 72% battery and recording; the device chip is tapped',
    run: (a) => _runHome(
        a,
        withData: true,
        AuditLive.pendant,
        pendantConnected: true,
        tap: find.byType(BatteryInfoWidget),
        action: 'Tap the device chip'),
  ),
  AuditScenario(
    id: 'home-capture-pendant-live',
    title: 'Pendant recording',
    page: _home,
    state: 'The pendant streams; 12:04 in',
    run: (a) => _runHome(a, withData: true, AuditLive.pendant, pendantConnected: true),
  ),
  AuditScenario(
    id: 'home-capture-pendant-paused',
    title: 'Pendant paused',
    page: _home,
    state: 'The user paused the pendant',
    run: (a) => _runHome(a, withData: true, AuditLive.pendantPaused, pendantConnected: true),
  ),
  AuditScenario(
    id: 'home-capture-pendant-tap',
    title: 'Switch to this phone while the pendant records',
    page: _home,
    state: 'The pendant streams; Recording from → This phone is tapped (the pendant asks first)',
    run: (a) async {
      await _runHome(a, withData: true, AuditLive.pendant, pendantConnected: true, tap: find.byType(BatteryInfoWidget));
      await a.tap(find.byKey(const Key('devices_this_phone')));
      await a.shot('Tap This phone in Recording from', step: 'switch');
    },
  ),
  AuditScenario(
    id: 'home-capture-phone-after-pendant',
    title: 'Phone recording after taking over from the pendant',
    page: _home,
    state: 'The phone records; the pendant waits for it',
    run: (a) => _runHome(a, withData: true, AuditLive.phoneAfterPendant, pendantConnected: true),
  ),
  AuditScenario(
    id: 'home-capture-phone-live',
    title: 'Phone recording, no pendant',
    page: _home,
    state: 'The phone records; 2:14 in',
    run: (a) => _runHome(a, withData: true, AuditLive.phone),
  ),
  AuditScenario(
    id: 'home-capture-call-live',
    title: 'Omi phone call',
    page: _home,
    state: 'An Omi call is active, 3:10 in',
    run: (a) => _runHome(a, withData: true, AuditLive.idle, call: true),
  ),
  AuditScenario(
    id: 'conversation-live-pendant',
    title: 'Live page, pendant',
    page: _live,
    state: 'The pendant records; two transcript lines',
    run: (a) => _runLivePage(a, AuditLive.pendant),
  ),
  AuditScenario(
    id: 'conversation-live-phone-paused',
    title: 'Live page, phone paused',
    page: _live,
    state: 'The phone recording is paused; two transcript lines',
    run: (a) => _runLivePage(a, AuditLive.phonePaused),
  ),
];
