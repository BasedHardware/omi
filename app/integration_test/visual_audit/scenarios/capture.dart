// Home's capture surfaces where the app really draws them: the live card at the top of Home, the
// record button to the right of the Ask Omi bar above the tab bar, the device chip in the header,
// the sheets they open, and the live page. The frame mirrors HomePage's layout; its Ask Omi bar
// is a copy of HomePage._buildChatBar (private there).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
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

/// Home as HomePage lays it out: header (device chip, settings), content, the tab bar, and the
/// [Ask Omi | record] row floating above it.
class _HomeFrame extends StatelessWidget {
  const _HomeFrame();

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
          HeaderCircleButton(
            semanticLabel: 'Settings',
            onTap: () {},
            icon: const FaIcon(FontAwesomeIcons.gear, size: 16, color: OmiColors.textSecondary),
          ),
        ]),
      ),
      body: Stack(children: [
        const HomeContentPage(),
        BottomNavBar(onTabTap: (_, __) {}),
        Positioned(
          left: 16,
          right: 16,
          bottom: bottomNavChatBarOffset(context),
          child: const Row(children: [Expanded(child: _AskOmiBar()), SizedBox(width: 10), HomeRecordButton()]),
        ),
      ]),
    );
  }
}

/// Copy of HomePage._buildChatBar's look.
class _AskOmiBar extends StatelessWidget {
  const _AskOmiBar();

  @override
  Widget build(BuildContext context) => Container(
        height: kHomeChatBarHeight,
        decoration: BoxDecoration(
          color: OmiColors.surface1,
          borderRadius: OmiRadius.pillAll,
          border: Border.all(color: OmiColors.border, width: 1),
        ),
        child: Row(children: [
          const SizedBox(width: 18),
          Expanded(child: Text('Ask Omi', style: OmiType.subhead.copyWith(color: OmiColors.textTertiary))),
          Container(
            width: 42,
            height: 42,
            margin: const EdgeInsets.only(right: 6),
            alignment: Alignment.center,
            decoration: const BoxDecoration(color: OmiColors.accent, shape: BoxShape.circle),
            child: const FaIcon(FontAwesomeIcons.microphone, size: 15, color: OmiColors.onAccent),
          ),
        ]),
      );
}

Future<void> _runHome(
  AuditRun a,
  AuditLive live, {
  bool pendantConnected = false,
  bool call = false,
  Finder? tap,
  Finder? longPress,
  String action = 'Home',
}) async {
  await a.pump(const _HomeFrame(), scaffold: false, providers: [
    ChangeNotifierProvider<DeviceProvider>.value(
        value: pendantConnected
            ? AuditDeviceProvider(connected: true, battery: 72, device: auditPendant)
            : AuditDeviceProvider()),
    ChangeNotifierProvider<CaptureProvider>.value(value: AuditCaptureProvider(live)),
    if (call) ChangeNotifierProvider<PhoneCallProvider>.value(value: _CallInProgress()),
  ]);
  if (tap != null) await a.tap(tap);
  if (longPress != null) await a.longPress(longPress);
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

const _home = 'lib/pages/home/page.dart (Home: live card, record button, device chip)';
const _live = 'lib/pages/conversation_capturing/page.dart (ConversationCapturingPage)';

final captureScenarios = <AuditScenario>[
  AuditScenario(
    id: 'home-header',
    title: 'Home, nothing recording, pendant connected',
    page: _home,
    state: 'An Omi pendant connected at 72% battery; nothing recording',
    run: (a) => _runHome(a, AuditLive.idle, pendantConnected: true),
  ),
  AuditScenario(
    id: 'home-capture-idle',
    title: 'Home, nothing recording, no pendant',
    page: _home,
    state: 'No device; nothing recording',
    run: (a) => _runHome(a, AuditLive.idle),
  ),
  AuditScenario(
    id: 'home-capture-pendant-live',
    title: 'Pendant recording',
    page: _home,
    state: 'The pendant streams; 12:04 in',
    run: (a) => _runHome(a, AuditLive.pendant, pendantConnected: true),
  ),
  AuditScenario(
    id: 'home-capture-pendant-paused',
    title: 'Pendant paused',
    page: _home,
    state: 'The user paused the pendant',
    run: (a) => _runHome(a, AuditLive.pendantPaused, pendantConnected: true),
  ),
  AuditScenario(
    id: 'home-capture-pendant-tap',
    title: 'Tap the record button while the pendant records',
    page: _home,
    state: 'The pendant streams; the record button is tapped',
    run: (a) => _runHome(a, AuditLive.pendant,
        pendantConnected: true, tap: find.byType(HomeRecordButton), action: 'Tap the record button'),
  ),
  AuditScenario(
    id: 'home-capture-phone-after-pendant',
    title: 'Phone recording after taking over from the pendant',
    page: _home,
    state: 'The phone records; the pendant waits for it',
    run: (a) => _runHome(a, AuditLive.phoneAfterPendant, pendantConnected: true),
  ),
  AuditScenario(
    id: 'home-capture-phone-live',
    title: 'Phone recording, no pendant',
    page: _home,
    state: 'The phone records; 2:14 in',
    run: (a) => _runHome(a, AuditLive.phone),
  ),
  AuditScenario(
    id: 'home-capture-call-live',
    title: 'Omi phone call',
    page: _home,
    state: 'An Omi call is active, 3:10 in',
    run: (a) => _runHome(a, AuditLive.idle, call: true),
  ),
  AuditScenario(
    id: 'home-capture-options',
    title: 'Other ways to record',
    page: _home,
    state: 'Nothing recording; the record button is held (the ⌄ badge opens the same sheet)',
    run: (a) async {
      await _runHome(a, AuditLive.idle, longPress: find.byType(HomeRecordButton), action: 'Hold the record button');
    },
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
