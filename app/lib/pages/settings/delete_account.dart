import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/core/app_shell.dart';
import 'package:omi/pages/settings/data_export.dart';
import 'package:omi/pages/settings/widgets/leave_flow_widgets.dart';
import 'package:omi/services/account_deletion_data.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:provider/provider.dart';

export 'package:omi/services/account_deletion_data.dart' show DeletionPendingData;
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/auth/finish_account_deletion.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// Account deletion: reason → feedback → typed confirmation. Each step is its own route, so the
/// iOS edge swipe and system back step back one step. This widget is step 1 and owns the flow.
class DeleteAccount extends StatefulWidget {
  const DeleteAccount({super.key, this.loadPendingData, this.pauseRecording});

  final Future<void> Function()? pauseRecording;

  /// Injected only for hermetic tests and renders; production loads the API and WAL store.
  final Future<DeletionPendingData?> Function()? loadPendingData;

  @override
  State<DeleteAccount> createState() => _DeleteAccountState();
}

/// What the reader has entered so far, shared by the three steps.
class _DeleteAccountFlow {
  _DeleteAccountFlow({this.loadPendingData, this.pauseRecording});

  final Future<void> Function()? pauseRecording;

  final Future<DeletionPendingData?> Function()? loadPendingData;
  final exit = LeaveFlowExit();
  final details = TextEditingController();
  final confirm = TextEditingController();
  String? reason;

  bool get offersPause => reason == 'taking_break' || reason == 'technical_issues';
  int get stepCount => offersPause ? 4 : 3;

  String? get detailsText => details.text.trim().isNotEmpty ? details.text.trim() : null;

  void dispose() {
    details.dispose();
    confirm.dispose();
  }
}

class _DeleteAccountState extends State<DeleteAccount> {
  late final _flow = _DeleteAccountFlow(loadPendingData: widget.loadPendingData, pauseRecording: widget.pauseRecording);

  static const _reasons = [
    _Reason('privacy_concerns', FontAwesomeIcons.shield),
    _Reason('not_using_enough', FontAwesomeIcons.clock),
    _Reason('missing_features', FontAwesomeIcons.puzzlePiece),
    _Reason('technical_issues', FontAwesomeIcons.triangleExclamation),
    _Reason('found_alternative', FontAwesomeIcons.arrowRightArrowLeft),
    _Reason('taking_break', FontAwesomeIcons.mugHot),
    _Reason('other', FontAwesomeIcons.ellipsis),
  ];

  @override
  void initState() {
    super.initState();
    PlatformManager.instance.analytics.deleteAccountFlowStarted();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _flow.exit.attach(context);
  }

  @override
  void dispose() {
    _flow.dispose();
    super.dispose();
  }

  String _label(String key) => switch (key) {
        'privacy_concerns' => context.l10n.deleteReasonPrivacy,
        'not_using_enough' => context.l10n.deleteReasonNotUsing,
        'missing_features' => context.l10n.deleteReasonMissingFeatures,
        'technical_issues' => context.l10n.deleteReasonTechnicalIssues,
        'found_alternative' => context.l10n.deleteReasonFoundAlternative,
        'taking_break' => context.l10n.deleteReasonTakingBreak,
        'other' => context.l10n.deleteReasonOther,
        _ => key,
      };

  @override
  Widget build(BuildContext context) {
    final reason = _flow.reason;
    return LeaveFlowStepScaffold(
      step: 0,
      stepCount: _flow.stepCount,
      title: context.l10n.deleteFlowReasonTitle,
      subtitle: context.l10n.deleteFlowReasonSubtitle,
      onPopInvoked: (didPop) {
        // Back button, system back and the edge swipe all leave through here.
        if (didPop && !_flow.exit.finished) {
          PlatformManager.instance.analytics.deleteAccountAbandoned(step: 1, reason: _flow.reason);
        }
      },
      body: ListView.separated(
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
        itemCount: _reasons.length,
        separatorBuilder: (_, __) => const SizedBox(height: OmiSpacing.xs),
        itemBuilder: (_, i) => LeaveFlowReasonTile(
          icon: _reasons[i].icon,
          label: _label(_reasons[i].key),
          selected: reason == _reasons[i].key,
          onTap: () => setState(() => _flow.reason = _reasons[i].key),
        ),
      ),
      actions: OmiButton(
        label: context.l10n.continueButton,
        expand: true,
        onPressed: reason == null
            ? null
            : () {
                PlatformManager.instance.analytics.deleteAccountReasonSelected(reason: reason);
                routeToPage(
                  context,
                  _flow.offersPause ? _DeletePauseInsteadStep(flow: _flow) : _DeleteFeedbackStep(flow: _flow),
                );
              },
      ),
    );
  }
}

/// Offered between the reason and feedback steps when the reason suggests a pause solves it:
/// recording stops, everything is kept, and the user can come back anytime. Pausing is the
/// primary action; continuing the deletion stays possible but secondary.
class _DeletePauseInsteadStep extends StatefulWidget {
  const _DeletePauseInsteadStep({required this.flow});

  final _DeleteAccountFlow flow;

  @override
  State<_DeletePauseInsteadStep> createState() => _DeletePauseInsteadStepState();
}

class _DeletePauseInsteadStepState extends State<_DeletePauseInsteadStep> {
  bool _pausing = false;
  _DeleteAccountFlow get flow => widget.flow;

  Future<void> _pause() async {
    setState(() => _pausing = true);
    try {
      if (flow.pauseRecording != null) {
        await flow.pauseRecording!();
      } else {
        final capture = context.read<CaptureProvider>();
        await capture.pauseCapture();
        // Also persist the device off toggle when no source is currently live.
        await capture.pauseDeviceRecording();
      }
      if (!mounted) return;
      OmiFeedback.confirm(context, context.l10n.deletePauseConfirmation);
      flow.exit.close(context);
    } catch (_) {
      if (mounted) {
        setState(() => _pausing = false);
        OmiFeedback.error(context, context.l10n.somethingWentWrong);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return LeaveFlowStepScaffold(
      step: 1,
      canPop: !_pausing,
      stepCount: flow.stepCount,
      title: context.l10n.deletePauseInsteadTitle,
      subtitle: context.l10n.deletePauseInsteadSubtitle,
      body: ListView(
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(OmiSpacing.md),
            decoration: BoxDecoration(
              color: OmiColors.surface1,
              borderRadius: OmiRadius.mdAll,
              border: Border.all(color: OmiColors.border),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  context.l10n.deletePauseRecordingLine,
                  style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, height: 1.5),
                ),
                const SizedBox(height: OmiSpacing.sm),
                Text(
                  context.l10n.deletePauseKeepLine,
                  style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, height: 1.5),
                ),
                const SizedBox(height: OmiSpacing.sm),
                Text(
                  context.l10n.deletePauseReturnLine,
                  style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, height: 1.5),
                ),
              ],
            ),
          ),
        ],
      ),
      actions: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          OmiButton(
            key: const Key('delete_pause_omi'),
            label: context.l10n.pauseOmiButton,
            expand: true,
            isLoading: _pausing,
            onPressed: _pausing ? null : _pause,
          ),
          const SizedBox(height: OmiSpacing.xs),
          OmiButton.secondary(
            key: const Key('delete_continue_deleting'),
            label: context.l10n.continueDeletingButton,
            expand: true,
            onPressed: _pausing ? null : () => routeToPage(context, _DeleteFeedbackStep(flow: flow)),
          ),
        ],
      ),
    );
  }
}

class _DeleteFeedbackStep extends StatelessWidget {
  const _DeleteFeedbackStep({required this.flow});

  final _DeleteAccountFlow flow;

  @override
  Widget build(BuildContext context) {
    void next() => routeToPage(context, _DeleteConfirmStep(flow: flow));
    return LeaveFlowStepScaffold(
      step: flow.offersPause ? 2 : 1,
      stepCount: flow.stepCount,
      title: context.l10n.deleteFlowFeedbackTitle,
      subtitle: context.l10n.deleteFlowFeedbackSubtitle,
      body: Align(
        alignment: Alignment.topCenter,
        child: SingleChildScrollView(
          child: LeaveFlowTextField(
            controller: flow.details,
            maxLength: 500,
            hint: context.l10n.deleteFlowFeedbackHint,
          ),
        ),
      ),
      actions: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          OmiButton(label: context.l10n.continueButton, expand: true, onPressed: next),
          const SizedBox(height: OmiSpacing.xs),
          OmiButton.tertiary(label: context.l10n.skipForNow, expand: true, onPressed: next),
        ],
      ),
    );
  }
}

class _DeleteConfirmStep extends StatefulWidget {
  const _DeleteConfirmStep({required this.flow});

  final _DeleteAccountFlow flow;

  @override
  State<_DeleteConfirmStep> createState() => _DeleteConfirmStepState();
}

class _DeleteConfirmStepState extends State<_DeleteConfirmStep> {
  bool _isDeleting = false;
  DeletionPendingData? _pending;
  bool _loadingPending = true;
  bool _pendingFailed = false;

  @override
  void initState() {
    super.initState();
    // The warning must reflect the moment of confirmation, not the moment the flow opened.
    _loadPending();
  }

  Future<void> _loadPending() async {
    try {
      final data = await (widget.flow.loadPendingData ?? loadDeletionPendingData)();
      if (mounted) {
        setState(() {
          _pending = data;
          _loadingPending = false;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _pendingFailed = true;
          _loadingPending = false;
        });
      }
    }
  }

  _DeleteAccountFlow get _flow => widget.flow;

  Future<void> _confirmDelete() async {
    if (_isDeleting) return;
    FocusScope.of(context).unfocus();
    setState(() => _isDeleting = true);
    final details = _flow.detailsText;

    try {
      final ok = await deleteAccount(reason: _flow.reason, reasonDetails: details);
      if (!mounted) return;
      if (!ok) {
        OmiFeedback.error(context, context.l10n.deleteAccountFailed);
        setState(() => _isDeleting = false);
        return;
      }
      PlatformManager.instance.analytics.deleteAccountConfirmed();
      PlatformManager.instance.analytics.deleteAccountFeedbackSubmitted(
        reason: _flow.reason ?? 'unspecified',
        details: details,
      );
      PlatformManager.instance.analytics.deleteUser();
      _flow.exit.finished = true;
      await clearFinishedDeletion(context);
      if (!mounted) return;
      routeToPage(context, const AppShell(), replace: true);
    } catch (_) {
      if (!mounted) return;
      OmiFeedback.error(context, context.l10n.deleteAccountFailed);
      setState(() => _isDeleting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final confirmWord = context.l10n.deleteConfirmationWord;
    return LeaveFlowStepScaffold(
      step: _flow.stepCount - 1,
      stepCount: _flow.stepCount,
      title: context.l10n.deleteFlowConfirmTitle,
      subtitle:
          _pending?.hasGrace != true ? context.l10n.deleteFlowConfirmSubtitle : context.l10n.deleteConfirmGraceSubtitle,
      canPop: !_isDeleting,
      // Keep typed confirmation with the buttons, above the keyboard.
      body: ListView(
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
        children: [
          if (_loadingPending) const Center(child: OmiSpinner()),
          if (_pendingFailed)
            OmiButton.secondary(
              label: context.l10n.retry,
              onPressed: () {
                setState(() {
                  _pendingFailed = false;
                  _loadingPending = true;
                });
                _loadPending();
              },
            ),
          if (_pending != null && (_pending!.hasGrace || _pending!.pendingCount > 0)) ...[
            _DeletionPendingNotice(data: _pending!),
            const SizedBox(height: OmiSpacing.md),
          ],
          OmiSettingsGroup(
            children: [
              OmiSettingsRow(
                leading: const FaIcon(FontAwesomeIcons.solidCommentDots),
                title: _pending?.hasGrace == true
                    ? context.l10n.deleteDataErasedAfterDays(_pending!.gracePeriodDays)
                    : context.l10n.allDataErased,
              ),
              OmiSettingsRow(
                  leading: const FaIcon(FontAwesomeIcons.puzzlePiece),
                  title: context.l10n.deleteAppsDisconnectImmediately),
              OmiSettingsRow(
                leading: const FaIcon(FontAwesomeIcons.creditCard),
                title: context.l10n.deleteSubscriptionImmediately,
              ),
            ],
          ),
          const SizedBox(height: OmiSpacing.md),
          OmiSettingsGroup(
            children: [
              ValueListenableBuilder<bool>(
                valueListenable: DataExport.exportInProgress,
                builder: (context, exporting, _) => OmiSettingsRow(
                  key: const Key('delete_account_export_row'),
                  leading: const FaIcon(FontAwesomeIcons.fileArrowDown),
                  title: context.l10n.exportAllData,
                  trailing: exporting ? const OmiSpinner(size: OmiSpinnerSize.small) : null,
                  showChevron: !exporting,
                  onTap: _isDeleting || exporting ? null : () => DataExport.run(context),
                ),
              ),
            ],
          ),
        ],
      ),
      actions: ValueListenableBuilder<TextEditingValue>(
        valueListenable: _flow.confirm,
        builder: (context, value, _) {
          final canDelete =
              !_isDeleting && !_loadingPending && !_pendingFailed && value.text.trim().toUpperCase() == confirmWord;
          return Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                context.l10n.deleteTypeToConfirm,
                style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: OmiSpacing.xs),
              TextField(
                key: const Key('delete_account_confirm_field'),
                controller: _flow.confirm,
                enabled: !_isDeleting,
                textCapitalization: TextCapitalization.characters,
                inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[A-Za-z]'))],
                style: OmiType.callout.copyWith(fontWeight: FontWeight.w600, letterSpacing: 2),
                decoration: leaveFlowInputDecoration(
                  hint: confirmWord,
                  focusColor: OmiColors.danger,
                ).copyWith(hintStyle: OmiType.callout.copyWith(color: OmiColors.textTertiary, letterSpacing: 2)),
              ),
              const SizedBox(height: OmiSpacing.md),
              // Delete is the primary once the word is typed; until then Keep is the only live action.
              OmiButton.destructive(
                label: context.l10n.deleteAccountTitle,
                expand: true,
                isLoading: _isDeleting,
                onPressed: canDelete || _isDeleting ? _confirmDelete : null,
              ),
              const SizedBox(height: OmiSpacing.xs),
              OmiButton.secondary(
                label: context.l10n.keepMyAccount,
                expand: true,
                onPressed: _isDeleting
                    ? null
                    : () {
                        PlatformManager.instance.analytics.deleteAccountKeptAccount(step: 3, reason: _flow.reason);
                        _flow.exit.close(context);
                      },
              ),
            ],
          );
        },
      ),
    );
  }
}

class _Reason {
  final String key;
  final FaIconData icon;
  const _Reason(this.key, this.icon);
}

/// Server-held recordings survive the reported grace window; phone-only audio does not.
class _DeletionPendingNotice extends StatelessWidget {
  const _DeletionPendingNotice({required this.data});

  final DeletionPendingData data;

  @override
  Widget build(BuildContext context) {
    final losing = data.notUploadedCount > 0 || (!data.hasGrace && data.processingCount > 0);
    final color = OmiColors.warning;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(OmiSpacing.sm),
      decoration: BoxDecoration(
        color: losing ? color.withValues(alpha: 0.12) : OmiColors.surface1,
        borderRadius: OmiRadius.mdAll,
        border: Border.all(color: losing ? color.withValues(alpha: 0.3) : OmiColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (data.processingCount > 0) ...[
            Text(
              data.hasGrace
                  ? context.l10n.deleteProcessingKept(data.processingCount, data.gracePeriodDays)
                  : context.l10n.deletePendingRecordingsWarning(data.processingCount),
              style: OmiType.footnote.copyWith(color: OmiColors.textPrimary, fontWeight: FontWeight.w600, height: 1.5),
            ),
            const SizedBox(height: OmiSpacing.xs),
          ],
          if (data.notUploadedCount > 0) ...[
            Text(
              context.l10n.deleteLocalRecordingsWarning(data.notUploadedCount),
              style: OmiType.footnote.copyWith(color: OmiColors.textPrimary, fontWeight: FontWeight.w600, height: 1.5),
            ),
            const SizedBox(height: OmiSpacing.xs),
          ],
          if (data.hasGrace)
            Text(
              context.l10n.deleteGracePeriodNotice(data.gracePeriodDays),
              style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, height: 1.5),
            ),
        ],
      ),
    );
  }
}
