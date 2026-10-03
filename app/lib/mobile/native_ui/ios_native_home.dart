import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api_presentation.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/conversations/widgets/capture_recovery_banner.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/pages/conversations/widgets/speaker_tag_prompt_card.dart';
import 'package:omi/pages/home/widgets/home_daily_recaps.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

import 'native_conversation_projection.dart';
import 'native_read_session.dart';

// LIFECYCLE: one-time
// DELETE-AFTER: https://github.com/BasedHardware/omi/issues/20426
const iosSwiftUiEnabled = bool.fromEnvironment('OMI_IOS_SWIFTUI');

Future<bool> supportsIosSwiftUi() async {
  if (!iosSwiftUiEnabled || !Platform.isIOS) return false;
  return await const MethodChannel('com.omi.native_ui/config').invokeMethod<bool>('isSupported') ?? false;
}

/// Stage one: SwiftUI renders the library; the current services still own every read and action.
class IosNativeHome extends StatefulWidget {
  const IosNativeHome({super.key, this.requestInitialLoad = true, this.loadRecaps});

  final bool requestInitialLoad;
  final RecentRecapsLoader? loadRecaps;

  @override
  State<IosNativeHome> createState() => IosNativeHomeState();
}

class IosNativeHomeState extends State<IosNativeHome> {
  final _recapsKey = GlobalKey<HomeDailyRecapsState>();
  final _headerScrollController = ScrollController();
  late final ConversationProvider _conversations;
  late final LocalRecordingsProvider _recordings;
  late final NativeReadSession _session;
  StreamSubscription<int>? _authSubscription;
  MethodChannel? _channel;
  int _revision = 0;
  int _viewGeneration = 0;
  bool _updateScheduled = false;

  @override
  void initState() {
    super.initState();
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
    if (widget.requestInitialLoad) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _session.active) _conversations.getInitialConversations();
      });
    }
  }

  void scrollToTop() {
    if (_headerScrollController.hasClients) _headerScrollController.jumpTo(0);
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
      'version': 1,
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
    };
  }

  Future<void> _publish() async {
    final channel = _channel;
    if (!mounted || channel == null) return;
    try {
      await channel.invokeMethod<void>(_session.active ? 'update' : 'invalidate', _session.active ? _snapshot() : null);
    } on MissingPluginException {
      // A disposed platform view removes its native handler before an in-flight update arrives.
      if (mounted && identical(channel, _channel)) rethrow;
    }
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
        await routeToPage(context, ConversationDetailPage(conversation: conversation));
      case 'browse':
        await routeToPage(
          context,
          Scaffold(
            appBar: AppBar(leading: const OmiBackButton(), title: Text(context.l10n.conversations)),
            body: const ConversationsPage(requestInitialLoad: false),
          ),
        );
      case 'refresh':
        context.read<CaptureProvider>().refreshInProgressConversations();
        await Future.wait([
          _conversations.getInitialConversations(),
          _recordings.refresh(),
          if (_recapsKey.currentState != null) _recapsKey.currentState!.refresh(),
        ]);
      case 'loadMore':
        await _conversations.getMoreConversationsFromServer();
      default:
        throw MissingPluginException('Unknown native presentation action');
    }
    if (mounted) await _publish();
    return null;
  }

  void _created(int id, int generation) {
    if (!mounted || !_session.active || generation != _viewGeneration) {
      unawaited(_invalidateChannel(MethodChannel('com.omi.native_ui/home/$id')));
      return;
    }
    _invalidate();
    _channel = MethodChannel('com.omi.native_ui/home/$id')..setMethodCallHandler(_handle);
    unawaited(_publish());
  }

  @override
  Widget build(BuildContext context) {
    context.watch<AppearanceProvider>();
    _scheduleUpdate();
    if (!_session.active) return const Center(child: OmiSpinner());
    final generation = _viewGeneration;
    return Column(
      children: [
        Flexible(
          child: SingleChildScrollView(
            controller: _headerScrollController,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const ConversationCaptureWidget(showsCall: true),
                const SpeechProfileCardWidget(),
                const UpdateFirmwareCardWidget(),
                const SpeakerTagPromptCard(),
                const CaptureRecoveryBanner(),
                if (widget.loadRecaps == null)
                  HomeDailyRecaps(key: _recapsKey)
                else
                  HomeDailyRecaps(key: _recapsKey, load: widget.loadRecaps!),
              ],
            ),
          ),
        ),
        Expanded(
          flex: 2,
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
    _headerScrollController.dispose();
    super.dispose();
  }
}
