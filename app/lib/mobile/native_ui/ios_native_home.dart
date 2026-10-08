import 'dart:async';
import 'dart:io';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/http/api_presentation.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/pages/conversations/widgets/live_capture_card.dart';
import 'package:omi/pages/home/widgets/home_daily_recaps.dart';
import 'package:omi/pages/conversations/daily_recaps_page.dart';
import 'package:omi/pages/conversations/widgets/daily_summaries_list.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import 'ios_native_feedback.dart';
import 'ios_native_surface.dart';
import 'native_conversation_projection.dart';
import 'native_read_session.dart';

// LIFECYCLE: one-time
// DELETE-AFTER: https://github.com/BasedHardware/omi/issues/20426
const iosSwiftUiEnabled = bool.fromEnvironment('OMI_IOS_SWIFTUI');

Future<bool> supportsIosSwiftUi() async {
  if (!iosSwiftUiEnabled || !Platform.isIOS) return false;
  final supported = await const MethodChannel('com.omi.native_ui/config').invokeMethod<bool>('isSupported') ?? false;
  // Feedback turns native only once the renderer is confirmed.
  if (supported) NativeFeedbackHost.confirmSupported();
  return supported;
}

Future<Set<String>>? _nativeUiCapabilities;

/// The host-rendered row kinds this iOS build compiled in, such as Apple's Shortcuts link (Siri
/// toolchain builds only). Flag-off and non-iOS builds answer {} without touching a channel, as does
/// a host without the handler or with a malformed answer. Resolved once per process.
Future<Set<String>> nativeUiCapabilities() {
  if (!IosNativeSurface.debugNativeHostForTest && !(iosSwiftUiEnabled && Platform.isIOS)) {
    return Future.value(const <String>{});
  }
  return _nativeUiCapabilities ??= _loadNativeUiCapabilities();
}

Future<Set<String>> _loadNativeUiCapabilities() async {
  try {
    final answer = await const MethodChannel('com.omi.native_ui/config').invokeMethod<Object?>('capabilities');
    if (answer is! List) return const <String>{};
    return Set.unmodifiable({
      for (final kind in answer)
        // Dart projects only the host kinds it knows; the host may answer fewer, never more.
        if (kind is String && nativeHostRowKinds.contains(kind)) kind,
    });
  } on MissingPluginException {
    return const <String>{};
  } on PlatformException {
    return const <String>{};
  }
}

/// Forgets the process answer so each test starts from an unresolved host.
@visibleForTesting
void debugResetNativeUiCapabilities() => _nativeUiCapabilities = null;

/// Stage one: SwiftUI renders the library; the current services still own every read and action.
/// A snapshot Swift refuses, or a view without a renderer, restores the classic Home for good.
class IosNativeHome extends StatefulWidget {
  const IosNativeHome(
      {super.key,
      this.requestInitialLoad = true,
      this.loadRecaps,
      this.header = const [],
      this.footer = const [],
      this.alerts = const [],
      this.fallback,
      this.onRejected});

  final bool requestInitialLoad;
  final RecentRecapsLoader? loadRecaps;
  final List<NativeHomeAction> header, footer, alerts;

  /// The Flutter Home shown once Swift refuses a snapshot; defaults to the classic conversation list.
  /// The route remembers the rejection, so a later Home in it starts here as well.
  final Widget? fallback;

  /// Lets an owner that presents more than Home, such as the native shell, restore its classic shell.
  final VoidCallback? onRejected;

  @override
  State<IosNativeHome> createState() => IosNativeHomeState();
}

class IosNativeHomeState extends State<IosNativeHome> {
  List<DailySummary> _recaps = [];
  CaptureCardPresentation? _capture;
  String? _captureKey;
  bool _captureScheduled = false;
  late final ConversationProvider _conversations;
  late final LocalRecordingsProvider _recordings;
  late final NativeReadSession _session;
  StreamSubscription<int>? _authSubscription;
  MethodChannel? _channel;
  int _revision = 0;
  int _viewGeneration = 0;
  bool _updateScheduled = false;
  bool _rejected = false;

  static const _rejection = 'omi.native_ui.home_rejected';

  @override
  void initState() {
    super.initState();
    // This route's renderer already refused a Home: start on the fallback, which owns the reads.
    _rejected = PageStorage.maybeOf(context)?.readState(context, identifier: _rejection) == true;
    _conversations = context.read<ConversationProvider>();
    _recordings = context.read<LocalRecordingsProvider>();
    final owner = AuthService.instance.captureSessionSnapshot();
    _session = NativeReadSession(
      isCurrent: () => owner != null && AuthService.instance.isSessionSnapshotCurrent(owner),
    );
    _conversations.addListener(_scheduleUpdate);
    _recordings.addListener(_scheduleUpdate);
    _authSubscription = AuthService.instance.sessionGenerationEvents.listen((_) {
      if (!_session.active) {
        _invalidate();
        if (mounted) setState(() {});
      }
    });
    if (_rejected) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) widget.onRejected?.call();
      });
      return;
    }
    if (widget.requestInitialLoad) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _session.active) _conversations.getInitialConversations();
      });
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) unawaited(_loadRecaps());
    });
  }

  void scrollToTop() {
    _invalidate();
    setState(() => _viewGeneration++);
  }

  void _scheduleUpdate() {
    if (!mounted || _updateScheduled) return;
    _updateScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _updateScheduled = false;
      if (mounted) unawaited(_publish());
    });
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  Map<String, Object?> _project(ServerConversation conversation, {bool includeDetail = false}) {
    final dates = OmiDateFormat.of(context);
    final names = SpeakerNames.forSegments(
      conversation.transcriptSegments,
      people: SharedPreferencesUtil().cachedPeople,
      l10n: context.l10n,
    );
    return projectNativeConversation(
      conversation,
      title: conversation.isLocked ? context.l10n.conversations : conversationRowTitle(context, conversation),
      lockedTitle: context.l10n.conversations,
      timestamp: dates.dateTime(conversation.startedAt ?? conversation.createdAt),
      speaker: (index) => names.forSegment(conversation.transcriptSegments[index]),
      includeDetail: includeDetail,
    );
  }

  Map<String, Object?> _snapshot() {
    final phase = _conversations.apiViewState.phase;
    final denied =
        phase == ApiViewPhase.authenticationRequired || phase == ApiViewPhase.terminal || phase == ApiViewPhase.locked;
    final visible = _session.active && !denied;
    final dates = OmiDateFormat.of(context);
    final seen = <String>{};
    final groups = <Map<String, Object?>>[
      if (visible && _conversations.processingConversations.isNotEmpty)
        {
          'id': 'processing',
          'title': context.l10n.processing,
          'conversations': [
            for (final conversation in _conversations.processingConversations)
              if (conversation.id.isNotEmpty && seen.add(conversation.id)) _project(conversation),
          ],
        },
      if (visible)
        for (final group in _conversations.groupedConversations.entries)
          {
            'id': group.key.toIso8601String(),
            'title': dates.dayHeader(group.key),
            'conversations': [
              for (final conversation in group.value)
                if (conversation.id.isNotEmpty && seen.add(conversation.id)) _project(conversation),
            ],
          },
    ];
    final l10n = context.l10n;
    return {
      'version': nativeSnapshotVersion,
      'nativeDetail': true,
      'revision': _revision++,
      'appearance': context.read<AppearanceProvider>().mode.name,
      'locale': Localizations.localeOf(context).toLanguageTag(),
      'direction': Directionality.of(context).name,
      'loading': _conversations.isLoadingConversations ||
          _conversations.isFetchingConversations ||
          _conversations.isAwaitingInitialFetchRetry,
      'failed': _conversations.conversationsLoadFailed || phase == ApiViewPhase.error || denied,
      'hasMore': visible && _conversations.hasMoreConversations,
      'localRecordingCount': visible ? _recordings.recordings.length : 0,
      'groups': groups,
      'copy': {
        'conversations': l10n.conversations,
        'summary': l10n.summary,
        'transcript': l10n.transcriptTab,
        'loading': l10n.loading,
        'empty': l10n.noConversationsYet,
        'error': l10n.connectionErrorDesc,
        'retry': l10n.retry,
        'more': l10n.moreOptions,
        'viewAll': l10n.viewAll,
        'loadMore': l10n.showMore,
        'recordings': l10n.recordings,
        'noSummary': l10n.conversationNoSummaryYet,
        'noTranscript': l10n.noTranscriptMessage,
        'starred': l10n.starred,
        'lockedHint': l10n.upgradeToUnlimited,
      },
      'chrome': {
        'home': l10n.home,
        'tasks': l10n.tasks,
        'ask': l10n.askOmi,
        'recapsTitle': l10n.dailyRecaps,
        'header': widget.header.map((action) => action.projection).toList(),
        'footer': widget.footer.map((action) => action.projection).toList(),
        'alerts': widget.alerts.map((action) => action.projection).toList(),
        'recaps': visible
            ? [
                for (final recap in _recaps)
                  {
                    'id': recap.id,
                    'title': recap.headline,
                    'date': recapDateLabel(context, recap.date),
                    'emoji': recap.dayEmoji,
                  }
              ]
            : <Object>[],
        'capture': visible ? _captureProjection() : null,
      },
    };
  }

  Map<String, Object?>? _captureProjection() {
    final presentation = _capture;
    if (presentation == null) return null;
    final card = presentation.card;
    return {
      'status': card.status,
      'detail': card.detail ?? '',
      'source': card.source,
      'elapsed': card.elapsed == null ? '' : LiveCaptureCard.formatElapsed(card.elapsed!),
      'lastLine': card.lastLine ?? '',
      'explanation': card.explanation ?? card.note ?? '',
      'actions': [
        if (card.onPauseToggle != null)
          {
            'id': 'pauseCapture',
            'title': card.paused ? context.l10n.resume : context.l10n.pause,
            'symbol': card.paused ? 'play.fill' : 'pause.fill',
            'enabled': true,
          },
        for (final (index, action) in presentation.controls.indexed)
          {
            'id': 'captureControl$index',
            'title': action.label,
            'symbol': action.symbol,
            'enabled': true,
          },
      ],
    };
  }

  void _captureChanged(CaptureCardPresentation? presentation) {
    _capture = presentation;
    if (_captureScheduled) return;
    _captureScheduled = true;
    scheduleMicrotask(() {
      _captureScheduled = false;
      if (!mounted || !_session.active) return;
      final key = jsonEncode(_captureProjection());
      if (key != _captureKey) {
        _captureKey = key;
        _scheduleUpdate();
      }
    });
  }

  Future<void> _loadRecaps() async {
    final result = await _session
        .read(() async => widget.loadRecaps != null ? widget.loadRecaps!() : getDailySummaries(limit: 3, offset: 0));
    if (!mounted || result == null) return;
    if (result.ok) {
      final seen = <String>{};
      _recaps = result.items.where((item) => item.id.isNotEmpty && seen.add(item.id)).toList();
    }
    _scheduleUpdate();
  }

  Future<void> _publish() async {
    final channel = _channel;
    if (!mounted || channel == null) return;
    try {
      await channel.invokeMethod<void>(_session.active ? 'update' : 'invalidate', _session.active ? _snapshot() : null);
    } on PlatformException catch (error) {
      // Swift refused the snapshot, whatever its revision: never leave a blank native Home.
      if (error.code != 'invalid_native_snapshot') rethrow;
      _reject();
    } on MissingPluginException {
      // A disposed platform view removes its native handler before an in-flight update arrives;
      // the current view without one has no renderer.
      if (mounted && identical(channel, _channel)) _reject();
    }
  }

  void _reject() {
    if (_rejected || !mounted) return;
    _rejected = true;
    PageStorage.maybeOf(context)?.writeState(context, true, identifier: _rejection);
    _invalidate();
    setState(() {});
    widget.onRejected?.call();
  }

  void _invalidate() {
    final channel = _channel;
    _channel = null;
    if (channel != null) {
      unawaited(_invalidateChannel(channel));
      channel.setMethodCallHandler(null);
    }
  }

  Future<void> _invalidateChannel(MethodChannel channel) async {
    try {
      await channel.invokeMethod<void>('invalidate');
    } on MissingPluginException {
      // The platform view already detached; there is no renderer left to invalidate.
    }
  }

  Future<Object?> _handle(MethodCall call) async {
    if (!mounted || !_session.active) {
      throw PlatformException(code: 'native_session_ended');
    }
    final id = call.arguments is String ? call.arguments as String : null;
    ServerConversation? conversation;
    for (final candidate in [..._conversations.displayedConversations, ..._conversations.processingConversations]) {
      if (candidate.id == id) {
        conversation = candidate;
        break;
      }
    }
    switch (call.method) {
      case 'detail':
        if (conversation == null) throw PlatformException(code: 'native_conversation_missing');
        final detail = await _session.read(() async {
          final result = await getConversationByIdResult(conversation!.id);
          return result.ok && result.item?.id == id ? result.item : null;
        });
        if (!mounted || detail == null) return null;
        return _project(detail, includeDetail: true);
      case 'open':
        if (conversation == null) throw PlatformException(code: 'native_conversation_missing');
        await openConversationListRow(context, _conversations, conversation);
      case 'browse':
        await routeToPage(
          context,
          const ConversationsPage(requestInitialLoad: false, nativeLibrary: true),
        );
      case 'refresh':
        context.read<CaptureProvider>().refreshInProgressConversations();
        await Future.wait([
          _conversations.getInitialConversations(),
          _recordings.refresh(),
          _loadRecaps(),
        ]);
      case 'loadMore':
        await _conversations.getMoreConversationsFromServer();
      case 'recaps':
        await routeToPage(context, const DailyRecapsPage());
      case 'recap':
        final matches = _recaps.where((item) => item.id == id);
        if (matches.isEmpty) throw PlatformException(code: 'native_recap_missing');
        final recap = matches.first;
        PlatformManager.instance.analytics.dailySummaryDetailViewed(summaryId: recap.id, date: recap.date);
        final result = await routeToPage(context, DailySummaryDetailPage(summaryId: recap.id, summary: recap));
        if (mounted && result is Map && result['deleted'] == true) _recaps.removeWhere((item) => item.id == recap.id);
      case 'capture':
        await _capture?.onOpen();
      case 'pauseCapture':
        _capture?.card.onPauseToggle?.call();
      default:
        final chrome =
            [...widget.header, ...widget.footer, ...widget.alerts].where((action) => action.id == call.method);
        if (chrome.isNotEmpty && chrome.first.enabled) {
          await chrome.first.perform();
        } else if (call.method.startsWith('captureControl')) {
          final index = int.tryParse(call.method.substring('captureControl'.length));
          final controls = _capture?.controls;
          if (index == null || controls == null || index >= controls.length || index < 0) {
            throw PlatformException(code: 'native_capture_control_missing');
          }
          controls[index].onTap();
        } else {
          throw MissingPluginException('Unknown native presentation action');
        }
    }
    if (mounted) await _publish();
    return null;
  }

  void _created(int id, int generation) {
    if (!mounted || !_session.active || _rejected || generation != _viewGeneration) {
      unawaited(_invalidateChannel(MethodChannel('com.omi.native_ui/home/$id')));
      return;
    }
    _invalidate();
    _channel = MethodChannel('com.omi.native_ui/home/$id')..setMethodCallHandler(_handle);
    unawaited(_publish());
  }

  @override
  Widget build(BuildContext context) {
    if (_rejected) {
      return widget.fallback ??
          ConversationsPage(requestInitialLoad: widget.requestInitialLoad, loadRecaps: widget.loadRecaps);
    }
    context.watch<AppearanceProvider>();
    _scheduleUpdate();
    if (!_session.active) return const Center(child: OmiSpinner());
    final generation = _viewGeneration;
    return Stack(
      fit: StackFit.expand,
      children: [
        Offstage(
          child: ConversationCaptureWidget(showsCall: true, onPresentation: _captureChanged),
        ),
        Positioned.fill(
          child: UiKitView(
            key: ValueKey('native-home-$_viewGeneration'),
            viewType: 'com.omi.native_ui/home',
            creationParams: _snapshot(),
            creationParamsCodec: const StandardMessageCodec(),
            onPlatformViewCreated: (id) => _created(id, generation),
          ),
        ),
      ],
    );
  }

  @override
  void dispose() {
    _session.dispose();
    _invalidate();
    _conversations.removeListener(_scheduleUpdate);
    _recordings.removeListener(_scheduleUpdate);
    unawaited(_authSubscription?.cancel());
    super.dispose();
  }
}

class NativeHomeAction {
  const NativeHomeAction(this.id, this.title, this.symbol, this.perform, {this.enabled = true});
  final String id, title, symbol;
  final FutureOr<void> Function() perform;
  final bool enabled;
  Map<String, Object?> get projection => {'id': id, 'title': title, 'symbol': symbol, 'enabled': enabled};
}
