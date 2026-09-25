import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/analytics/product_telemetry.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/services/experiments/experiment_registry.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/experiments/experiment_builder.dart';
import 'package:omi/widgets/app_review_prompt.dart';
import 'package:omi/ui/ui.dart';
import 'package:visibility_detector/visibility_detector.dart';
import 'package:uuid/uuid.dart';

import 'feedback_prompt_policy.dart';

class SummaryTab extends StatefulWidget {
  final bool reviewEnabled;
  final String searchQuery;
  final int currentResultIndex;
  final VoidCallback? onTapWhenSearchEmpty;

  const SummaryTab(
      {super.key,
      this.reviewEnabled = false,
      this.searchQuery = '',
      this.currentResultIndex = -1,
      this.onTapWhenSearchEmpty});

  @override
  State<SummaryTab> createState() => _SummaryTabState();
}

class _SummaryTabState extends State<SummaryTab> with AutomaticKeepAliveClientMixin {
  bool _isEditing = false;
  @override
  bool get wantKeepAlive => true;

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final transcriptionProvider = context.watch<ConversationDetailProvider>();
    final conversationId = transcriptionProvider.conversationOrNull?.id;
    if (transcriptionProvider.loadingReprocessTranscription &&
        conversationId != null &&
        transcriptionProvider.reprocessConversationId == conversationId) {
      return Padding(
        padding: const EdgeInsets.only(top: 18.0),
        child: OmiLoadingState(label: context.l10n.retranscribingConversation),
      );
    }
    return GestureDetector(
      excludeFromSemantics: true,
      behavior: HitTestBehavior.translucent,
      onTap: () {
        FocusScope.of(context).unfocus();
        // If search is empty, call the callback to close search
        if (widget.searchQuery.isEmpty && widget.onTapWhenSearchEmpty != null) {
          widget.onTapWhenSearchEmpty!();
        }
      },
      child: Consumer<ConversationDetailProvider>(
        builder: (context, provider, child) {
          final conversation = provider.conversationOrNull;
          final discarded = conversation?.discarded ?? true;
          final summarySelection = provider.getSummarySelection();
          // App-result summaries require result coordinates for trustworthy
          // feedback provenance. Keep this prompt on the canonical overview /
          // sections population until that wire is available.
          final hasSummaryFeedback =
              !discarded && !summarySelection.isApp && summarySelection.content.trim().isNotEmpty;
          final hasRecordingFeedback = !discarded &&
              conversation != null &&
              conversation.status == ConversationStatus.completed &&
              conversation.audioFiles.isNotEmpty;
          final feedbackKind = conversation == null
              ? null
              : feedbackPromptKindForTarget(
                  targetId: conversation.id,
                  hasSummary: hasSummaryFeedback,
                  hasRecording: hasRecordingFeedback,
                );
          return AppReviewPrompt(
            contentId: conversation?.id ?? '',
            moment: AppReviewMoment.conversationRead,
            enabled: widget.reviewEnabled &&
                !_isEditing &&
                !provider.isLoading &&
                !provider.loadingReprocessConversation &&
                !provider.loadingReprocessTranscription &&
                conversation?.status == ConversationStatus.completed &&
                !discarded &&
                provider.getSummarySelection().content.trim().isNotEmpty,
            child: Stack(
              children: [
                CustomScrollView(
                  keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.manual,
                  slivers: [
                    // Title and facts live in the page header, shared by every tab.
                    const SliverToBoxAdapter(child: SizedBox(height: 4)),
                    discarded
                        ? const SliverToBoxAdapter(child: ReprocessDiscardedWidget())
                        : GetAppsWidgets(
                            searchQuery: widget.searchQuery,
                            currentResultIndex: widget.currentResultIndex,
                            canStartEditing: () {
                              final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
                              if (!connectivityProvider.isConnected) {
                                ConnectivityProvider.showNoInternetDialog(context);
                                return false;
                              }
                              return true;
                            },
                            onEditStarted: (_) {
                              setState(() => _isEditing = true);
                              PlatformManager.instance.analytics.editSummaryStarted();
                            },
                            onEditCancelled: (_) {
                              setState(() => _isEditing = false);
                              PlatformManager.instance.analytics.editSummaryCancelled();
                            },
                            onSaveSummarySelection: (selection, newContent) {
                              PlatformManager.instance.analytics.editSummarySaved();
                              context.read<ConversationDetailProvider>().saveEditingSummarySelection(
                                    selection,
                                    newContent,
                                  );
                            },
                          ),
                    if (feedbackKind == FeedbackPromptKind.summary)
                      SummaryFeedbackPrompt(
                        key: ValueKey('summary-feedback-${conversation?.id ?? ''}'),
                        conversationId: conversation?.id,
                      ),
                    if (feedbackKind == FeedbackPromptKind.recording && conversation != null)
                      RecordingQualityFeedbackPrompt(
                        key: ValueKey('recording-feedback-${conversation.id}'),
                        recordingId: conversation.id,
                      ),
                    const SliverToBoxAdapter(child: GetGeolocationWidgets()),
                    const SliverToBoxAdapter(child: SizedBox(height: 150)),
                  ],
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

/// A sparse, object-level usefulness prompt for generated summaries. The
/// attempt starts when the prompt is actually eligible/visible and only
/// completes successfully after the server accepts the rating.
class SummaryFeedbackPrompt extends StatefulWidget {
  final String? conversationId;

  const SummaryFeedbackPrompt({super.key, required this.conversationId});

  @override
  State<SummaryFeedbackPrompt> createState() => _SummaryFeedbackPromptState();
}

/// A separate recording-quality prompt keeps audio/transcription problems
/// distinct from usefulness of the generated summary. The recording target is
/// the conversation's server-owned recording-session key.
class RecordingQualityFeedbackPrompt extends StatefulWidget {
  final String? recordingId;

  const RecordingQualityFeedbackPrompt({super.key, required this.recordingId});

  @override
  State<RecordingQualityFeedbackPrompt> createState() => _RecordingQualityFeedbackPromptState();
}

class _RecordingQualityFeedbackPromptState extends State<RecordingQualityFeedbackPrompt> {
  ProductAttempt? _attempt;
  bool _dismissed = false;
  bool _responded = false;
  bool _saving = false;
  bool _visible = false;
  bool? _eligible;
  bool _policyClaimed = false;
  Future<void>? _claimFuture;
  String? _feedbackId;
  int? _pendingValue;

  @override
  void initState() {
    super.initState();
    _loadEligibility();
  }

  Future<void> _loadEligibility() async {
    final id = widget.recordingId;
    if (id == null || id.isEmpty) return;
    final identityEpoch = AnalyticsManager.identityEpoch;
    final eligible = await FeedbackPromptPolicy.instance.canShow(id);
    if (!mounted || id != widget.recordingId || identityEpoch != AnalyticsManager.identityEpoch) return;
    setState(() => _eligible = eligible);
  }

  Future<void> _claimIfVisible() {
    if (!_visible || _policyClaimed || _eligible != true) return Future<void>.value();
    final pending = _claimFuture;
    if (pending != null) return pending;
    final id = widget.recordingId;
    if (id == null || id.isEmpty) return Future<void>.value();
    final identityEpoch = AnalyticsManager.identityEpoch;
    late final Future<void> tracked;
    tracked = _performClaim(id, identityEpoch).whenComplete(() {
      if (identical(_claimFuture, tracked)) _claimFuture = null;
    });
    _claimFuture = tracked;
    return tracked;
  }

  Future<void> _performClaim(String id, int identityEpoch) async {
    bool claimed;
    try {
      claimed = await FeedbackPromptPolicy.instance.claim(id);
    } catch (_) {
      claimed = false;
    }
    if (!mounted || id != widget.recordingId || identityEpoch != AnalyticsManager.identityEpoch) return;
    if (!claimed) {
      setState(() => _eligible = false);
      return;
    }
    setState(() => _policyClaimed = true);
    _ensureExposed();
  }

  void _ensureExposed() {
    if (_attempt != null || _dismissed || _responded || !_visible || !_policyClaimed) return;
    final id = widget.recordingId;
    if (id == null || id.isEmpty) return;
    _attempt = ProductTelemetry.instance.start(
      ProductJourney.recordingFeedback,
      surface: ProductSurface.conversationDetail,
      objectId: RecordReference.fromId(id),
    );
  }

  Future<void> _submit(int value) async {
    if (_saving || _responded) return;
    final id = widget.recordingId;
    if (id == null || id.isEmpty) return;
    final identityEpoch = AnalyticsManager.identityEpoch;
    await _claimIfVisible();
    if (!mounted || id != widget.recordingId || identityEpoch != AnalyticsManager.identityEpoch) return;
    _ensureExposed();
    if (_attempt == null) return;
    if (_pendingValue != value) {
      _feedbackId = const Uuid().v4();
      _pendingValue = value;
    }
    final feedbackId = _feedbackId;
    final attempt = _attempt;
    setState(() => _saving = true);
    MobileFeedbackReceipt? receipt;
    try {
      receipt = await submitMobileFeedback(
        kind: MobileFeedbackKind.recordingQuality,
        targetKind: MobileFeedbackTargetKind.conversation,
        targetId: id,
        value: value,
        feedbackId: feedbackId,
        correlationId: _attempt?.correlationId,
      );
    } catch (_) {
      receipt = null;
    }
    if (!mounted) return;
    if (identityEpoch != AnalyticsManager.identityEpoch || !identical(attempt, _attempt)) {
      attempt?.complete(ProductOutcome.superseded);
      if (identical(attempt, _attempt)) {
        setState(() => _saving = false);
        _attempt = null;
      }
      return;
    }
    if (receipt == null) {
      _attempt?.complete(ProductOutcome.failure, failure: ProductFailure.unknown);
      _attempt = null;
      setState(() => _saving = false);
      return;
    }
    _attempt?.complete(ProductOutcome.success);
    unawaited(FeedbackPromptPolicy.instance.recordDecision(id));
    setState(() {
      _responded = true;
      _saving = false;
    });
  }

  Future<void> _dismiss() async {
    if (_responded || _dismissed || _saving) return;
    final id = widget.recordingId;
    if (id == null || id.isEmpty) return;
    final identityEpoch = AnalyticsManager.identityEpoch;
    await _claimIfVisible();
    if (!mounted || id != widget.recordingId || identityEpoch != AnalyticsManager.identityEpoch) return;
    _ensureExposed();
    _attempt?.complete(ProductOutcome.cancelled);
    unawaited(FeedbackPromptPolicy.instance.recordDecision(id));
    setState(() => _dismissed = true);
  }

  @override
  void dispose() {
    if (!_responded && !_dismissed && _attempt != null) {
      _attempt!.complete(ProductOutcome.unobserved);
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.recordingId == null || widget.recordingId!.isEmpty || _dismissed || _responded || _eligible != true) {
      return const SliverToBoxAdapter(child: SizedBox.shrink());
    }
    return SliverToBoxAdapter(
      child: VisibilityDetector(
        key: ValueKey('recording-feedback-visibility-${widget.recordingId}'),
        onVisibilityChanged: (info) {
          final visible = info.visibleFraction > 0;
          if (visible == _visible || !mounted) return;
          setState(() => _visible = visible);
          if (visible) unawaited(_claimIfVisible());
        },
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 4),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        context.l10n.feedbackTitleAudioQuality,
                        style: OmiType.footnote.copyWith(fontWeight: FontWeight.w500),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        context.l10n.feedbackSubtitleAudioQuality,
                        style: OmiType.caption.copyWith(color: OmiColors.textSecondary),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  tooltip: context.l10n.wasThisHelpful,
                  onPressed: _saving || !_policyClaimed ? null : () => _submit(1),
                  icon: const Icon(Icons.thumb_up_alt_outlined, size: 19),
                  color: Colors.white70,
                ),
                IconButton(
                  tooltip: context.l10n.notHelpful,
                  onPressed: _saving || !_policyClaimed ? null : () => _submit(-1),
                  icon: const Icon(Icons.thumb_down_alt_outlined, size: 19),
                  color: Colors.white70,
                ),
                IconButton(
                  tooltip: context.l10n.close,
                  onPressed: _saving || !_policyClaimed ? null : _dismiss,
                  icon: const Icon(Icons.close, size: 18),
                  color: Colors.white54,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _SummaryFeedbackPromptState extends State<SummaryFeedbackPrompt> {
  ProductAttempt? _attempt;
  bool _dismissed = false;
  bool _responded = false;
  bool _saving = false;
  bool? _eligible;
  bool _visible = false;
  bool _policyClaimed = false;
  Future<void>? _claimFuture;
  String? _feedbackId;
  int? _pendingValue;

  @override
  void initState() {
    super.initState();
    _loadEligibility();
  }

  @override
  void didUpdateWidget(covariant SummaryFeedbackPrompt oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.conversationId != widget.conversationId) {
      _attempt?.complete(ProductOutcome.superseded);
      _attempt = null;
      _dismissed = false;
      _responded = false;
      _saving = false;
      _eligible = null;
      _visible = false;
      _policyClaimed = false;
      _claimFuture = null;
      _feedbackId = null;
      _pendingValue = null;
      _loadEligibility();
    }
  }

  Future<void> _loadEligibility() async {
    final id = widget.conversationId;
    if (id == null || id.isEmpty) return;
    final identityEpoch = AnalyticsManager.identityEpoch;
    final eligible = await FeedbackPromptPolicy.instance.canShow(id);
    if (!mounted || id != widget.conversationId || identityEpoch != AnalyticsManager.identityEpoch) return;
    setState(() => _eligible = eligible);
  }

  Future<void> _claimIfVisible() {
    if (!_visible || _policyClaimed || _eligible != true) return Future<void>.value();
    final pending = _claimFuture;
    if (pending != null) return pending;
    final id = widget.conversationId;
    if (id == null || id.isEmpty) return Future<void>.value();
    final identityEpoch = AnalyticsManager.identityEpoch;
    late final Future<void> tracked;
    tracked = _performClaim(id, identityEpoch).whenComplete(() {
      if (identical(_claimFuture, tracked)) _claimFuture = null;
    });
    _claimFuture = tracked;
    return tracked;
  }

  Future<void> _performClaim(String id, int identityEpoch) async {
    bool claimed;
    try {
      claimed = await FeedbackPromptPolicy.instance.claim(id);
    } catch (_) {
      claimed = false;
    }
    if (!mounted || id != widget.conversationId || identityEpoch != AnalyticsManager.identityEpoch) return;
    if (!claimed) {
      setState(() => _eligible = false);
      return;
    }
    setState(() => _policyClaimed = true);
    // ExperimentBuilder owns the exposure ordering when a lease is present;
    // its selected builder starts the attempt after the lease paints.
    if (AnalyticsManager().experiments == null) _ensureExposed();
  }

  void _ensureExposed() {
    if (_attempt != null || _dismissed || _responded || _eligible != true || !_visible || !_policyClaimed) return;
    final id = widget.conversationId;
    if (id == null || id.isEmpty) return;
    _attempt = ProductTelemetry.instance.start(
      ProductJourney.summaryFeedback,
      surface: ProductSurface.conversationDetail,
      objectId: RecordReference.fromId(id),
    );
  }

  Future<void> _submit(int value) async {
    if (_saving || _responded) return;
    final id = widget.conversationId;
    if (id == null || id.isEmpty) return;
    final identityEpoch = AnalyticsManager.identityEpoch;
    await _claimIfVisible();
    if (!mounted || id != widget.conversationId || identityEpoch != AnalyticsManager.identityEpoch) return;
    _ensureExposed();
    if (_attempt == null) return;
    if (_pendingValue != value) {
      _feedbackId = const Uuid().v4();
      _pendingValue = value;
    }
    final feedbackId = _feedbackId;
    final attempt = _attempt;
    setState(() => _saving = true);
    MobileFeedbackReceipt? receipt;
    try {
      receipt = await submitMobileFeedback(
        kind: MobileFeedbackKind.summaryHelpfulness,
        targetKind: MobileFeedbackTargetKind.conversation,
        targetId: id,
        value: value,
        feedbackId: feedbackId,
        correlationId: _attempt?.correlationId,
      );
    } catch (_) {
      receipt = null;
    }
    if (!mounted) return;
    if (identityEpoch != AnalyticsManager.identityEpoch || !identical(attempt, _attempt)) {
      attempt?.complete(ProductOutcome.superseded);
      if (identical(attempt, _attempt)) {
        setState(() => _saving = false);
        _attempt = null;
      }
      return;
    }
    if (receipt == null) {
      _attempt?.complete(ProductOutcome.failure, failure: ProductFailure.unknown);
      _attempt = null;
      setState(() => _saving = false);
      return;
    }
    _attempt?.complete(ProductOutcome.success);
    unawaited(FeedbackPromptPolicy.instance.recordDecision(id));
    if (value > 0) {
      ProductTelemetry.instance.value(
        ProductValue.feedbackHelpful,
        surface: ProductSurface.conversationDetail,
        objectId: RecordReference.fromId(id),
      );
    }
    setState(() {
      _responded = true;
      _saving = false;
    });
  }

  Future<void> _dismiss() async {
    if (_responded || _dismissed) return;
    final id = widget.conversationId;
    if (id == null || id.isEmpty) return;
    final identityEpoch = AnalyticsManager.identityEpoch;
    await _claimIfVisible();
    if (!mounted || id != widget.conversationId || identityEpoch != AnalyticsManager.identityEpoch) return;
    _ensureExposed();
    _attempt?.complete(ProductOutcome.cancelled);
    unawaited(FeedbackPromptPolicy.instance.recordDecision(id));
    setState(() => _dismissed = true);
  }

  @override
  void dispose() {
    if (!_responded && !_dismissed && _attempt != null) {
      _attempt!.complete(ProductOutcome.unobserved);
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.conversationId == null ||
        widget.conversationId!.isEmpty ||
        _dismissed ||
        _responded ||
        _eligible != true) {
      return const SliverToBoxAdapter(child: SizedBox.shrink());
    }
    final experiments = AnalyticsManager().experiments;
    final prompt = experiments == null
        ? _buildPrompt(context, compact: false, waitForExperimentExposure: false)
        : ExperimentBuilder<SummaryFeedbackLayout>(
            service: experiments,
            definition: MobileExperiments.summaryFeedbackLayout,
            surface: 'summary-feedback',
            visible: _visible && _policyClaimed,
            loadingBuilder: _buildLoadingPrompt,
            builder: (context, layout, child) => _buildPrompt(
              context,
              compact: layout == SummaryFeedbackLayout.compact,
              waitForExperimentExposure: true,
            ),
          );
    return SliverToBoxAdapter(
      child: VisibilityDetector(
        key: ValueKey('summary-feedback-visibility-${widget.conversationId}'),
        onVisibilityChanged: (info) {
          final visible = info.visibleFraction > 0;
          if (visible == _visible || !mounted) return;
          setState(() => _visible = visible);
          if (visible) unawaited(_claimIfVisible());
        },
        child: prompt,
      ),
    );
  }

  Widget _buildLoadingPrompt(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.fromLTRB(20, 12, 20, 8),
      child: SizedBox(
        height: 48,
        child: DecoratedBox(
          decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
        ),
      ),
    );
  }

  Widget _buildPrompt(BuildContext context, {required bool compact, required bool waitForExperimentExposure}) {
    if (waitForExperimentExposure) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _visible && _policyClaimed) _ensureExposed();
      });
    }
    return Padding(
      padding: EdgeInsets.fromLTRB(20, compact ? 8 : 12, 20, compact ? 4 : 8),
      child: Container(
        padding: EdgeInsets.symmetric(horizontal: compact ? 10 : 16, vertical: compact ? 6 : 12),
        decoration: BoxDecoration(
          color: OmiColors.surface1,
          borderRadius: BorderRadius.circular(compact ? 12 : 16),
        ),
        child: Row(
          children: [
            Expanded(
              child: Text(
                context.l10n.wasThisHelpful,
                style: TextStyle(color: Colors.white, fontSize: compact ? 13 : 14, fontWeight: FontWeight.w500),
              ),
            ),
            IconButton(
              tooltip: context.l10n.wasThisHelpful,
              onPressed: _saving || !_policyClaimed ? null : () => _submit(1),
              icon: Icon(Icons.thumb_up_alt_outlined, size: compact ? 18 : 19),
              color: Colors.white70,
            ),
            IconButton(
              tooltip: context.l10n.notHelpful,
              onPressed: _saving || !_policyClaimed ? null : () => _submit(-1),
              icon: Icon(Icons.thumb_down_alt_outlined, size: compact ? 18 : 19),
              color: Colors.white70,
            ),
            IconButton(
              tooltip: context.l10n.close,
              onPressed: _saving || !_policyClaimed ? null : _dismiss,
              icon: Icon(Icons.close, size: compact ? 17 : 18),
              color: Colors.white54,
            ),
          ],
        ),
      ),
    );
  }
}
